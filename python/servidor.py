# import zmq

# context = zmq.Context()
# socket = context.socket(zmq.REP)
# socket.connect("tcp://broker:5556")

# while True:
#     message = socket.recv()
#     print(f"Mensagem recebida: {message}", flush=True)
    
#     if message == b"login":
#         socket.send_string("recebi o login")
#     else:
#         socket.send_string("mensagem desconhecida")
import os
import re
import signal
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import msgpack
import zmq

SERVER_ID = os.getenv("SERVER_ID", "server-1")
BROKER_BACKEND_URL = os.getenv("BROKER_BACKEND_URL", "tcp://broker:5556")
DB_PATH = os.getenv("DB_PATH", "/app/data/server.db")
PUB_BIND_PORT = int(os.getenv("PUB_BIND_PORT", "7000"))
PEER_SUB_URLS = [url.strip() for url in os.getenv("PEER_SUB_URLS", "").split(",") if url.strip()]

USER_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")
CHANNEL_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")

running = True
processed_events_lock = threading.Lock()
processed_events: set[str] = set()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize(message: dict[str, Any]) -> bytes:
    return msgpack.packb(message, use_bin_type=True)


def deserialize(payload: bytes) -> dict[str, Any]:
    return msgpack.unpackb(payload, raw=False)


def ensure_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS logins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            request_id TEXT,
            user TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            origin_server TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            name TEXT NOT NULL UNIQUE,
            created_by TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            origin_server TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_events (
            event_id TEXT PRIMARY KEY,
            origin_server TEXT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """
    )
    conn.commit()

    for row in cur.execute("SELECT event_id FROM processed_events"):
        processed_events.add(row[0])

    conn.close()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def mark_processed(conn: sqlite3.Connection, event_id: str, origin: str, event_type: str, timestamp: str) -> None:
    with processed_events_lock:
        if event_id in processed_events:
            return
        conn.execute(
            "INSERT OR IGNORE INTO processed_events(event_id, origin_server, event_type, timestamp) VALUES (?, ?, ?, ?)",
            (event_id, origin, event_type, timestamp),
        )
        conn.commit()
        processed_events.add(event_id)


def validate_user(user: str) -> bool:
    return bool(USER_REGEX.fullmatch(user or ""))


def validate_channel(channel: str) -> bool:
    return bool(CHANNEL_REGEX.fullmatch(channel or ""))


def log_login(conn: sqlite3.Connection, user: str, timestamp: str, origin: str, event_id: str, request_id: str = "") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO logins(event_id, request_id, user, timestamp, origin_server) VALUES (?, ?, ?, ?, ?)",
        (event_id, request_id, user, timestamp, origin),
    )
    conn.commit()
    mark_processed(conn, event_id, origin, "login", timestamp)


def create_channel(conn: sqlite3.Connection, channel: str, user: str, timestamp: str, origin: str, event_id: str) -> tuple[bool, str | None]:
    try:
        conn.execute(
            "INSERT INTO channels(event_id, name, created_by, timestamp, origin_server) VALUES (?, ?, ?, ?, ?)",
            (event_id, channel, user, timestamp, origin),
        )
        conn.commit()
        mark_processed(conn, event_id, origin, "create_channel", timestamp)
        return True, None
    except sqlite3.IntegrityError:
        mark_processed(conn, event_id, origin, "create_channel", timestamp)
        return False, "channel_exists"


def list_channels(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM channels ORDER BY name ASC").fetchall()
    return [row[0] for row in rows]


def build_response(request: dict[str, Any], status: str, data: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
    return {
        "type": "response",
        "operation": request.get("operation"),
        "request_id": request.get("request_id"),
        "timestamp": now_iso(),
        "server_id": SERVER_ID,
        "status": status,
        "data": data or {},
        "error": error,
    }


def publish_replication(pub_socket: zmq.Socket, event: dict[str, Any]) -> None:
    payload = serialize(event)
    pub_socket.send(payload)
    print(f"[{SERVER_ID}] PUBLICOU replicação: {event}", flush=True)


def replication_listener(sub_socket: zmq.Socket) -> None:
    conn = get_conn()
    while running:
        try:
            if sub_socket.poll(500):
                payload = sub_socket.recv()
                event = deserialize(payload)
                print(f"[{SERVER_ID}] RECEBEU replicação: {event}", flush=True)
                origin = event.get("origin_server")
                event_id = event.get("event_id")
                event_type = event.get("event_type")
                timestamp = event.get("timestamp", now_iso())
                if not event_id or origin == SERVER_ID:
                    continue
                with processed_events_lock:
                    if event_id in processed_events:
                        continue
                if event_type == "login":
                    log_login(conn, event["user"], timestamp, origin, event_id, event.get("request_id", ""))
                elif event_type == "create_channel":
                    create_channel(conn, event["channel"], event["user"], timestamp, origin, event_id)
        except zmq.error.ContextTerminated:
            break
        except Exception as exc:
            print(f"[{SERVER_ID}] ERRO replicação: {exc}", flush=True)
    conn.close()


def handle_request(conn: sqlite3.Connection, pub_socket: zmq.Socket, request: dict[str, Any]) -> dict[str, Any]:
    operation = request.get("operation")
    user = request.get("user", "")
    timestamp = request.get("timestamp", now_iso())
    request_id = request.get("request_id", str(uuid.uuid4()))
    event_id = str(uuid.uuid4())

    if operation == "login":
        if not validate_user(user):
            return build_response(request, "error", error="invalid_username")

        log_login(conn, user, timestamp, SERVER_ID, event_id, request_id)
        publish_replication(
            pub_socket,
            {
                "event_type": "login",
                "event_id": event_id,
                "request_id": request_id,
                "timestamp": timestamp,
                "origin_server": SERVER_ID,
                "user": user,
            },
        )
        return build_response(request, "ok", {"message": f"login realizado para {user}"})

    if operation == "create_channel":
        channel = request.get("data", {}).get("channel", "")
        if not validate_user(user):
            return build_response(request, "error", error="invalid_username")
        if not validate_channel(channel):
            return build_response(request, "error", error="invalid_channel_name")

        created, error = create_channel(conn, channel, user, timestamp, SERVER_ID, event_id)
        if not created:
            return build_response(request, "error", error=error)

        publish_replication(
            pub_socket,
            {
                "event_type": "create_channel",
                "event_id": event_id,
                "timestamp": timestamp,
                "origin_server": SERVER_ID,
                "user": user,
                "channel": channel,
            },
        )
        return build_response(request, "ok", {"channel": channel, "message": "canal criado"})

    if operation == "list_channels":
        channels = list_channels(conn)
        return build_response(request, "ok", {"channels": channels})

    return build_response(request, "error", error="unknown_operation")


def main() -> None:
    global running
    ensure_db()

    context = zmq.Context()

    rep_socket = context.socket(zmq.REP)
    rep_socket.connect(BROKER_BACKEND_URL)

    pub_socket = context.socket(zmq.PUB)
    pub_socket.bind(f"tcp://0.0.0.0:{PUB_BIND_PORT}")

    sub_socket = context.socket(zmq.SUB)
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
    for url in PEER_SUB_URLS:
        sub_socket.connect(url)

    print(
        f"[{SERVER_ID}] Iniciado | broker={BROKER_BACKEND_URL} | db={DB_PATH} | pub_port={PUB_BIND_PORT} | peers={PEER_SUB_URLS}",
        flush=True,
    )

    listener = threading.Thread(target=replication_listener, args=(sub_socket,), daemon=True)
    listener.start()

    conn = get_conn()

    def stop_handler(signum, frame):
        global running
        running = False
        print(f"[{SERVER_ID}] Encerrando por sinal {signum}", flush=True)

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    try:
        while running:
            if rep_socket.poll(500):
                payload = rep_socket.recv()
                request = deserialize(payload)
                print(f"[{SERVER_ID}] RECEBEU requisição: {request}", flush=True)
                response = handle_request(conn, pub_socket, request)
                rep_socket.send(serialize(response))
                print(f"[{SERVER_ID}] ENVIOU resposta: {response}", flush=True)
    finally:
        conn.close()
        rep_socket.close(0)
        pub_socket.close(0)
        sub_socket.close(0)
        context.term()
        print(f"[{SERVER_ID}] Finalizado", flush=True)


if __name__ == "__main__":
    main()
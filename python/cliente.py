# import zmq
# from time import sleep

# context = zmq.Context()
# socket = context.socket(zmq.REQ)
# socket.connect("tcp://broker:5555")

# i = 0
# while True:
#     socket.send(b"login")
#     mensagem = socket.recv()
#     print(f"{mensagem}")
#     i += 1
#     sleep(0.5)
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import msgpack
import zmq

CLIENT_ID = os.getenv("CLIENT_ID", "bot-1")
BROKER_URL = os.getenv("BROKER_URL", "tcp://broker:5555")
AUTO_CHANNEL = os.getenv("AUTO_CHANNEL", "geral")
STARTUP_DELAY = float(os.getenv("STARTUP_DELAY", "3"))
STEP_DELAY = float(os.getenv("STEP_DELAY", "0.8"))
LOGIN_RETRIES = int(os.getenv("LOGIN_RETRIES", "5"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize(message: dict[str, Any]) -> bytes:
    return msgpack.packb(message, use_bin_type=True)


def deserialize(payload: bytes) -> dict[str, Any]:
    return msgpack.unpackb(payload, raw=False)


def build_request(operation: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "request",
        "operation": operation,
        "request_id": str(uuid.uuid4()),
        "timestamp": now_iso(),
        "user": CLIENT_ID,
        "data": data or {},
    }


def send_request(socket: zmq.Socket, request: dict[str, Any]) -> dict[str, Any]:
    print(f"[CLIENTE {CLIENT_ID}] ENVIANDO: {request}", flush=True)
    socket.send(serialize(request))
    payload = socket.recv()
    response = deserialize(payload)
    print(f"[CLIENTE {CLIENT_ID}] RECEBEU: {response}", flush=True)
    return response


def main() -> None:
    print(f"[CLIENTE {CLIENT_ID}] aguardando {STARTUP_DELAY}s para iniciar", flush=True)
    time.sleep(STARTUP_DELAY)

    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect(BROKER_URL)
    socket.setsockopt(zmq.LINGER, 0)

    try:
        login_ok = False
        for attempt in range(1, LOGIN_RETRIES + 1):
            response = send_request(socket, build_request("login"))
            if response.get("status") == "ok":
                login_ok = True
                break
            print(f"[CLIENTE {CLIENT_ID}] login falhou, tentativa {attempt}/{LOGIN_RETRIES}", flush=True)
            time.sleep(STEP_DELAY)

        if not login_ok:
            print(f"[CLIENTE {CLIENT_ID}] não conseguiu fazer login", flush=True)
            return

        time.sleep(STEP_DELAY)
        response = send_request(socket, build_request("list_channels"))
        channels = response.get("data", {}).get("channels", []) if response.get("status") == "ok" else []

        time.sleep(STEP_DELAY)
        if AUTO_CHANNEL not in channels:
            send_request(socket, build_request("create_channel", {"channel": AUTO_CHANNEL}))
        else:
            print(f"[CLIENTE {CLIENT_ID}] canal '{AUTO_CHANNEL}' já existia", flush=True)

        time.sleep(STEP_DELAY)
        send_request(socket, build_request("list_channels"))
        print(f"[CLIENTE {CLIENT_ID}] fluxo concluído com sucesso", flush=True)
    finally:
        socket.close(0)
        context.term()


if __name__ == "__main__":
    main()
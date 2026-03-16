# import zmq

# context = zmq.Context()
# poller = zmq.Poller()

# client_socket = context.socket(zmq.ROUTER)
# client_socket.bind("tcp://*:5555")
# poller.register(client_socket, zmq.POLLIN)
# client_count = 0

# server_socket = context.socket(zmq.DEALER)
# server_socket.bind("tcp://*:5556")
# poller.register(server_socket, zmq.POLLIN)
# server_count = 0

# while True:
#     socks = dict(poller.poll())

#     if socks.get(client_socket) == zmq.POLLIN:
#         client_count += 1
#         message = client_socket.recv()
#         more = client_socket.getsockopt(zmq.RCVMORE)
#         if more:
#             server_socket.send(message, zmq.SNDMORE)
#         else:
#             server_socket.send(message)
#         print(f"Client messages: {client_count}", flush=True)

#     if socks.get(server_socket) == zmq.POLLIN:
#         server_count += 1
#         message = server_socket.recv()
#         more = server_socket.getsockopt(zmq.RCVMORE)
#         if more:
#             client_socket.send(message, zmq.SNDMORE)
#         else:
#             client_socket.send(message)
#         print(f"Server messages: {server_count}", flush=True)

import os
import signal
import sys
import time
from typing import Any

import msgpack
import zmq

FRONTEND_BIND = os.getenv("BROKER_FRONTEND_BIND", "tcp://*:5555")
BACKEND_BIND = os.getenv("BROKER_BACKEND_BIND", "tcp://*:5556")


def safe_unpack(frame: bytes) -> Any:
    try:
        return msgpack.unpackb(frame, raw=False)
    except Exception:
        try:
            return frame.decode("utf-8", errors="replace")
        except Exception:
            return repr(frame)


def log_multipart(direction: str, frames: list[bytes]) -> None:
    tail = safe_unpack(frames[-1]) if frames else None
    print(
        f"[BROKER] {direction} | frames={len(frames)} | payload={tail}",
        flush=True,
    )


def main() -> None:
    context = zmq.Context()
    frontend = context.socket(zmq.ROUTER)
    backend = context.socket(zmq.DEALER)

    frontend.bind(FRONTEND_BIND)
    backend.bind(BACKEND_BIND)

    print(
        f"[BROKER] Iniciado | frontend={FRONTEND_BIND} | backend={BACKEND_BIND}",
        flush=True,
    )

    poller = zmq.Poller()
    poller.register(frontend, zmq.POLLIN)
    poller.register(backend, zmq.POLLIN)

    running = True

    def stop_handler(signum, frame):
        nonlocal running
        running = False
        print(f"[BROKER] Encerrando por sinal {signum}", flush=True)

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    try:
        while running:
            events = dict(poller.poll(1000))

            if frontend in events:
                frames = frontend.recv_multipart()
                log_multipart("cliente -> servidor", frames)
                backend.send_multipart(frames)

            if backend in events:
                frames = backend.recv_multipart()
                log_multipart("servidor -> cliente", frames)
                frontend.send_multipart(frames)
    finally:
        frontend.close(0)
        backend.close(0)
        context.term()
        print("[BROKER] Finalizado", flush=True)


if __name__ == "__main__":
    main()
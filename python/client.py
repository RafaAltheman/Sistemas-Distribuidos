import zmq
import msgpack
import time
import random

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://broker:5555")

def send(msg):
    socket.send(msgpack.packb(msg))
    return msgpack.unpackb(socket.recv(), raw=False)

user = f"bot_{random.randint(1000,9999)}"

print(f"[BOT] Iniciando como {user}")

while True:
    print("\n--- NOVO CICLO ---")

    resp = send({
        "type": "login",
        "user": user,
        "timestamp": time.time()
    })
    print("[LOGIN]", resp)


    channel_name = f"canal_{random.randint(1,300)}"

    resp = send({
        "type": "create_channel",
        "user": user,
        "channel": channel_name,
        "timestamp": time.time()
    })
    print("[CREATE CHANNEL]", resp)


    resp = send({
        "type": "list_channels",
        "user": user,
        "timestamp": time.time()
    })
    print("[LIST CHANNELS]", resp)

    time.sleep(0.2)

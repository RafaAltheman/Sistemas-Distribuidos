import zmq
from time import sleep

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://broker:5555")

i = 0
while True:
    socket.send(b"login")
    mensagem = socket.recv()
    print(f"{mensagem}")
    i += 1
    sleep(0.5)

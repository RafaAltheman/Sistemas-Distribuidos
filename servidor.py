import zmq

context = zmq.Context()
socket = context.socket(zmq.REP)
socket.connect("tcp://broker:5556")

while True:
    message = socket.recv()
    print(f"Mensagem recebida: {message}", flush=True)
    
    if message == b"login":
        socket.send_string("recebi o login")
    else:
        socket.send_string("mensagem desconhecida")

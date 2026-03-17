import zmq
import msgpack


def safe_unpack(data: bytes):
    try:
        return msgpack.unpackb(data, raw=False)
    except Exception:
        return '<payload binario>'


def main():
    context = zmq.Context()
    frontend = context.socket(zmq.ROUTER)
    backend = context.socket(zmq.DEALER)
    frontend.bind('tcp://*:5555')
    backend.bind('tcp://*:5556')
    print('[BROKER] Iniciado | frontend=tcp://*:5555 | backend=tcp://*:5556', flush=True)

    poller = zmq.Poller()
    poller.register(frontend, zmq.POLLIN)
    poller.register(backend, zmq.POLLIN)

    while True:
        events = dict(poller.poll())
        if frontend in events:
            frames = frontend.recv_multipart()
            payload = safe_unpack(frames[-1]) if frames else None
            print(f'[BROKER] cliente -> servidor | frames={len(frames)} | payload={payload}', flush=True)
            backend.send_multipart(frames)
        if backend in events:
            frames = backend.recv_multipart()
            payload = safe_unpack(frames[-1]) if frames else None
            print(f'[BROKER] servidor -> cliente | frames={len(frames)} | payload={payload}', flush=True)
            frontend.send_multipart(frames)


if __name__ == '__main__':
    main()

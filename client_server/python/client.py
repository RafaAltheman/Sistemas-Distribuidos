import os
import time
import uuid
from datetime import datetime, timezone

import msgpack
import zmq


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def send_request(socket, user, operation, data=None):
    req = {
        'type': 'request', 'operation': operation, 'request_id': str(uuid.uuid4()),
        'timestamp': iso_now(), 'user': user, 'data': data or {}
    }
    print(f'[CLIENTE {user}] ENVIANDO: {req}', flush=True)
    socket.send(msgpack.packb(req, use_bin_type=True))
    raw = socket.recv()
    resp = msgpack.unpackb(raw, raw=False)
    print(f'[CLIENTE {user}] RECEBEU: {resp}', flush=True)
    return resp


if __name__ == '__main__':
    user = os.environ.get('CLIENT_USER', 'bot_python')
    start_delay = float(os.environ.get('START_DELAY', '5'))
    channel = os.environ.get('CHANNEL_TO_CREATE', 'geral')
    print(f'[CLIENTE {user}] aguardando {start_delay}s para iniciar', flush=True)
    time.sleep(start_delay)
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect('tcp://broker:5555')

    send_request(socket, user, 'login')
    time.sleep(1)
    channels = send_request(socket, user, 'list_channels')
    time.sleep(1)
    existing = (channels.get('data') or {}).get('channels', [])
    if channel not in existing:
        send_request(socket, user, 'create_channel', {'channel': channel})
        time.sleep(1)
    send_request(socket, user, 'list_channels')
    print(f'[CLIENTE {user}] fluxo concluído com sucesso', flush=True)

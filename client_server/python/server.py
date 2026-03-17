import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone

import msgpack
import zmq


def iso_now():
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('CREATE TABLE IF NOT EXISTS logins (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, ts TEXT)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created_by TEXT, ts TEXT)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS replication_events (event_id TEXT PRIMARY KEY, payload BLOB)')
        self.conn.commit()

    def add_login(self, user: str, ts: str):
        self.conn.execute('INSERT INTO logins(user, ts) VALUES (?, ?)', (user, ts))
        self.conn.commit()

    def channel_exists(self, name: str) -> bool:
        cur = self.conn.execute('SELECT 1 FROM channels WHERE name = ?', (name,))
        return cur.fetchone() is not None

    def add_channel(self, name: str, user: str, ts: str):
        self.conn.execute('INSERT OR IGNORE INTO channels(name, created_by, ts) VALUES (?, ?, ?)', (name, user, ts))
        self.conn.commit()

    def list_channels(self):
        cur = self.conn.execute('SELECT name FROM channels ORDER BY name')
        return [r[0] for r in cur.fetchall()]

    def seen_event(self, event_id: str) -> bool:
        cur = self.conn.execute('SELECT 1 FROM replication_events WHERE event_id = ?', (event_id,))
        return cur.fetchone() is not None

    def save_event(self, event_id: str, payload: bytes):
        self.conn.execute('INSERT OR IGNORE INTO replication_events(event_id, payload) VALUES (?, ?)', (event_id, payload))
        self.conn.commit()


class Server:
    def __init__(self):
        self.server_id = os.environ['SERVER_ID']
        self.db_path = os.environ.get('DB_PATH', f'/app/data/{self.server_id}.db')
        self.pub_port = int(os.environ.get('PUB_PORT', '7000'))
        peers_raw = os.environ.get('PEER_PUBS', '')
        self.peers = [p.strip() for p in peers_raw.split(',') if p.strip()]
        self.storage = Storage(self.db_path)
        self.context = zmq.Context()
        self.rep = self.context.socket(zmq.REP)
        self.rep.connect('tcp://broker:5556')
        self.pub = self.context.socket(zmq.PUB)
        self.pub.bind(f'tcp://*:{self.pub_port}')
        self.sub = self.context.socket(zmq.SUB)
        self.sub.setsockopt(zmq.SUBSCRIBE, b'')
        for peer in self.peers:
            self.sub.connect(peer)
        self.poller = zmq.Poller()
        self.poller.register(self.rep, zmq.POLLIN)
        self.poller.register(self.sub, zmq.POLLIN)

    def valid_channel(self, channel: str) -> bool:
        return bool(re.fullmatch(r'[A-Za-z0-9_\-]{1,32}', channel or ''))

    def send_replication(self, event: dict):
        payload = msgpack.packb(event, use_bin_type=True)
        self.storage.save_event(event['event_id'], payload)
        time.sleep(0.2)
        self.pub.send(payload)
        print(f'[{self.server_id}] PUBLICOU replicação: {event}', flush=True)

    def apply_replication(self, event: dict, raw: bytes):
        event_id = event.get('event_id')
        if not event_id or self.storage.seen_event(event_id):
            return
        self.storage.save_event(event_id, raw)
        if event.get('origin_server') == self.server_id:
            return
        if event.get('event_type') == 'login':
            self.storage.add_login(event['user'], event['timestamp'])
        elif event.get('event_type') == 'create_channel':
            channel = event.get('channel')
            if channel:
                self.storage.add_channel(channel, event.get('user', ''), event.get('timestamp', iso_now()))
        print(f'[{self.server_id}] RECEBEU replicação: {event}', flush=True)

    def handle(self, req: dict) -> dict:
        op = req.get('operation')
        request_id = req.get('request_id')
        user = req.get('user', '')
        timestamp = req.get('timestamp', iso_now())
        if op == 'login':
            if not user:
                return self.response(op, request_id, 'error', None, 'usuario obrigatorio')
            self.storage.add_login(user, timestamp)
            self.send_replication({
                'event_type': 'login', 'event_id': str(uuid.uuid4()), 'request_id': request_id,
                'timestamp': timestamp, 'origin_server': self.server_id, 'user': user,
            })
            return self.response(op, request_id, 'ok', {'message': f'login realizado para {user}'}, None)
        if op == 'list_channels':
            return self.response(op, request_id, 'ok', {'channels': self.storage.list_channels()}, None)
        if op == 'create_channel':
            data = req.get('data') or {}
            channel = data.get('channel', '')
            if not self.valid_channel(channel):
                return self.response(op, request_id, 'error', None, 'nome de canal invalido')
            if self.storage.channel_exists(channel):
                return self.response(op, request_id, 'error', {'channel': channel}, 'canal ja existe')
            self.storage.add_channel(channel, user, timestamp)
            self.send_replication({
                'event_type': 'create_channel', 'event_id': str(uuid.uuid4()),
                'timestamp': timestamp, 'origin_server': self.server_id,
                'user': user, 'channel': channel,
            })
            return self.response(op, request_id, 'ok', {'channel': channel, 'message': 'canal criado'}, None)
        return self.response(op, request_id, 'error', None, 'operacao invalida')

    def response(self, op, request_id, status, data, error):
        return {
            'type': 'response', 'operation': op, 'request_id': request_id,
            'timestamp': iso_now(), 'server_id': self.server_id,
            'status': status, 'data': data, 'error': error,
        }

    def run(self):
        print(f'[{self.server_id}] Iniciado | broker=tcp://broker:5556 | db={self.db_path} | pub_port={self.pub_port} | peers={self.peers}', flush=True)
        time.sleep(1.0)
        while True:
            events = dict(self.poller.poll(1000))
            if self.rep in events:
                raw = self.rep.recv()
                req = msgpack.unpackb(raw, raw=False)
                print(f'[{self.server_id}] RECEBEU requisição: {req}', flush=True)
                resp = self.handle(req)
                print(f'[{self.server_id}] ENVIOU resposta: {resp}', flush=True)
                self.rep.send(msgpack.packb(resp, use_bin_type=True))
            if self.sub in events:
                raw = self.sub.recv()
                unpacker = msgpack.Unpacker(raw=False)
                unpacker.feed(raw)
                try:
                    event = next(unpacker)
                except StopIteration:
                    continue
                self.apply_replication(event, raw)


if __name__ == '__main__':
    Server().run()

"""Separate structured storage, ready for a future Oura importer."""
import json
from datetime import date
from contextlib import contextmanager
import sqlite3
from pathlib import Path


class OuraStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS oura_records (
                kind TEXT NOT NULL, id TEXT NOT NULL, day TEXT NOT NULL,
                payload_json TEXT NOT NULL, imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(kind, id))''')
            db.execute("CREATE INDEX IF NOT EXISTS oura_day ON oura_records(day)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def upsert(self, kind, record):
        with self.connect() as db:
            db.execute('''INSERT INTO oura_records(kind,id,day,payload_json) VALUES(?,?,?,?)
                ON CONFLICT(kind,id) DO UPDATE SET day=excluded.day,
                payload_json=excluded.payload_json, imported_at=CURRENT_TIMESTAMP''',
                (kind, record["id"], record["day"], json.dumps(record)))

    def read_range(self, start, end):
        with self.connect() as db:
            return [{"kind": kind, "data": json.loads(payload)} for kind, payload in db.execute(
                "SELECT kind,payload_json FROM oura_records WHERE day BETWEEN ? AND ? ORDER BY day,kind,id", (start, end))]

    def import_records(self, kind, records):
        if kind not in ('daily_sleep', 'daily_readiness', 'daily_activity', 'sleep',
                        'daily_spo2', 'sleep_time', 'daily_stress'):
            raise ValueError('Unsupported Oura summary type.')
        rows = []
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get('id'), str) or not record['id']:
                raise ValueError('Oura summary is missing its record ID.')
            day = record.get('day')
            if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                raise ValueError('Invalid Oura summary date.')
            rows.append((kind, record['id'], day, json.dumps(record)))
        with self.connect() as db:
            db.executemany('''INSERT INTO oura_records(kind,id,day,payload_json) VALUES(?,?,?,?)
                ON CONFLICT(kind,id) DO UPDATE SET day=excluded.day,
                payload_json=excluded.payload_json, imported_at=CURRENT_TIMESTAMP''', rows)

    def inventory(self, start=None):
        with self.connect() as db:
            return [{'kind': kind, 'count': count, 'start': start, 'end': end}
                    for kind, count, start, end in db.execute(
                        'SELECT kind,COUNT(*),MIN(day),MAX(day) FROM oura_records WHERE day >= ? GROUP BY kind',
                        (start or '0001-01-01',))]

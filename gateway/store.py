import hashlib
import secrets
import sqlite3
import time


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS grants(token TEXT PRIMARY KEY, expires REAL);
            CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, token TEXT UNIQUE,
                revoked INTEGER NOT NULL DEFAULT 0, consent_version TEXT, consent_at REAL);
            CREATE TABLE IF NOT EXISTS customers(token TEXT PRIMARY KEY, quota INTEGER, used INTEGER DEFAULT 0);
        ''')

    def grant(self):
        token = secrets.token_urlsafe(32)
        with self.db:
            self.db.execute("INSERT INTO grants VALUES (?, ?)", (digest(token), time.time() + 86400))
        return token

    def customer(self, quota):
        if type(quota) is not int or quota <= 0:
            raise ValueError("positive quota required")
        token = secrets.token_urlsafe(32)
        with self.db:
            self.db.execute("INSERT INTO customers VALUES (?, ?, 0)", (digest(token), quota))
        return token

    def enroll(self, grant, version):
        token, device = secrets.token_urlsafe(32), secrets.token_hex(16)
        with self.db:
            cur = self.db.execute("DELETE FROM grants WHERE token=? AND expires>?", (digest(grant), time.time()))
            if cur.rowcount != 1:
                raise ValueError("invalid enrollment")
            self.db.execute("INSERT INTO devices VALUES (?, ?, 0, ?, ?)", (device, digest(token), version, time.time()))
        return dict(device_id=device, token=token)

    def device(self, token):
        row = self.db.execute("SELECT id FROM devices WHERE token=? AND revoked=0", (digest(token),)).fetchone()
        return row[0] if row else None

    def revoke(self, token):
        device = self.device(token)
        with self.db:
            self.db.execute("UPDATE devices SET revoked=1 WHERE token=?", (digest(token),))
        return device

    def valid_customer(self, token):
        row = self.db.execute("SELECT quota,used FROM customers WHERE token=?", (digest(token),)).fetchone()
        return bool(row and row[1] < row[0])

    def consume(self, token, count):
        if type(count) is not int or count < 0:
            raise ValueError("invalid amount")
        with self.db:
            cur = self.db.execute("UPDATE customers SET used=used+? WHERE token=? AND used+?<=quota",
                                  (count, digest(token), count))
            if cur.rowcount != 1:
                raise ValueError("customer quota exceeded")

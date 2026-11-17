import json
import sqlite3
import threading


class Storage:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, received_at TEXT,
          device TEXT, port TEXT, source TEXT, session INTEGER, raw TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, category TEXT, payload TEXT);
        CREATE INDEX IF NOT EXISTS artifact_category ON artifacts(category);
        """)
        self.db.commit()

    def record(self, r):
        with self.lock, self.db:
            self.db.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?,?)",
                            (r.id, r.received_at, r.device, r.port, r.source, r.session,
                             r.raw, json.dumps(r.as_dict(), ensure_ascii=False)))

    def save(self, category, data):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO artifacts VALUES(?,?,?)",
                            (data["id"], category, json.dumps(data, ensure_ascii=False)))

    def history(self, category, limit=100):
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute(
                "SELECT payload FROM artifacts WHERE category=? ORDER BY rowid DESC LIMIT ?", (category, limit))]

    def raw_records(self, limit=10000):
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute("SELECT payload FROM records ORDER BY rowid DESC LIMIT ?", (limit,))][::-1]

    def close(self):
        with self.lock:
            self.db.close()

"""SQLite single-host store. A revision CAS prevents stale checkpoint writes.

Full task data stays private; public event projection is stored separately.
Deploy one App Server worker; this is not a distributed job scheduler.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=str)


class SessionStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, token_hash TEXT NOT NULL,
                    revision INTEGER NOT NULL, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                    kind TEXT NOT NULL, time REAL NOT NULL, public TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_session ON events(session_id, seq);
                CREATE TABLE IF NOT EXISTS checkpoints (
                    session_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    state TEXT NOT NULL, time REAL NOT NULL,
                    PRIMARY KEY(session_id, revision));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, query: str):
        sid, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        state = {"id": sid, "revision": 0, "status": "queued", "query": query,
                 "objective": query, "turn": 1, "step": 0,
                 "blocks": [[{"role": "user", "content": query}]], "memory": "", "query_pinned": False,
                 "pending": [], "ledger": {}, "results": [], "approval": None,
                 "current_action": None, "action_history": [], "input_request": None,
                 "wait": None, "final": None, "created_at": time.time()}
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES (?,?,?,?)",
                       (sid, hashlib.sha256(token.encode()).hexdigest(), 0, encode(state)))
        return state, token

    def authenticate(self, sid: str, token: str):
        with self.connect() as db:
            row = db.execute("SELECT token_hash FROM sessions WHERE id=?", (sid,)).fetchone()
        return bool(row and hmac.compare_digest(row[0], hashlib.sha256(token.encode()).hexdigest()))

    def get(self, sid: str):
        with self.connect() as db:
            row = db.execute("SELECT state FROM sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            raise KeyError(sid)
        return json.loads(row[0])

    def save(self, state: dict):
        revision = state["revision"]
        snapshot = dict(state, revision=revision + 1)
        with self.connect() as db:
            changed = db.execute("UPDATE sessions SET state=?,revision=? WHERE id=? AND revision=?",
                (encode(snapshot), revision + 1, state["id"], revision)).rowcount
            if changed != 1:
                raise RuntimeError("Session revision conflict")
            db.execute("INSERT INTO checkpoints VALUES (?,?,?,?)",
                       (state["id"], revision + 1, encode(snapshot), time.time()))
        state["revision"] = revision + 1

    def event(self, sid: str, kind: str, public: dict):
        now = time.time()
        with self.connect() as db:
            seq = db.execute("INSERT INTO events(session_id,kind,time,public) VALUES (?,?,?,?)",
                             (sid, kind, now, encode(public))).lastrowid
        return {"id": seq, "session_id": sid, "kind": kind, "time": now, **public}

    def events(self, sid: str, after: int = 0):
        with self.connect() as db:
            rows = db.execute("SELECT seq,kind,time,public FROM events WHERE session_id=? AND seq>? ORDER BY seq LIMIT 200",
                              (sid, after)).fetchall()
        return [{"id": seq, "kind": kind, "time": ts, **json.loads(body)} for seq, kind, ts, body in rows]

    def recover(self):
        """On exclusive application startup, mark unfinished work, never replay it."""
        with self.connect() as db:
            rows = db.execute("SELECT state FROM sessions").fetchall()
        recovered = []
        for (body,) in rows:
            state = json.loads(body)
            if state["status"] in {"running", "queued"}:
                state["status"] = "interrupted"
                self.save(state)
                recovered.append(state["id"])
        return recovered

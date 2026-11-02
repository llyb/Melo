"""Application directory and checkpoint references; graph owns all message/file bodies."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4


def now():
    return datetime.now(UTC).isoformat()


class SessionCatalog:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported catalog version")
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("""CREATE TABLE IF NOT EXISTS turn_requests
                (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id)
                 ON DELETE CASCADE, data TEXT NOT NULL)""")
            db.execute("PRAGMA user_version=1")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, sid, deleting=False):
        with self.connection() as db:
            row = db.execute("SELECT data FROM sessions WHERE id=?", (sid,)).fetchone()
        if row is None:
            raise KeyError(sid)
        session = json.loads(row[0])
        if session["lifecycle"] != "active" and not deleting:
            raise KeyError(sid)
        return session

    def all(self):
        with self.connection() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT data FROM sessions")]

    @staticmethod
    def summary(session):
        return {k: session[k] for k in ("id", "title", "created_at", "updated_at", "revision")}

    def list(self, limit, offset):
        # shortcut: local catalog sorts in memory; add indexed columns if directory size hurts latency.
        rows = sorted((s for s in self.all() if s["lifecycle"] == "active"),
                      key=lambda s: (s["updated_at"], s["id"]), reverse=True)
        return {"items": [self.summary(s) for s in rows[offset:offset + limit]],
                "has_more": len(rows) > offset + limit}

    def save(self, session):
        with self.connection() as db:
            db.execute("UPDATE sessions SET data=? WHERE id=?",
                       (json.dumps(session), session["id"]))

    def create(self):
        session = {"id": str(uuid4()), "title": "新会话", "title_manual": False,
                       "created_at": now(), "updated_at": now(), "revision": 0,
                       "head_checkpoint_id": None, "lifecycle": "active"}
        with self.connection() as db:
            db.execute("INSERT INTO sessions VALUES (?,?)", (session["id"], json.dumps(session)))
        return self.summary(session)

    def rename(self, sid, title):
        session = self.get(sid)
        session.update(title=title, title_manual=True, updated_at=now())
        self.save(session)
        return self.summary(session)

    def mark_deleting(self, sid):
        session = self.get(sid, deleting=True)
        session["lifecycle"] = "deleting"
        self.save(session)

    def remove(self, sid):
        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE id=?", (sid,))

    def request(self, turn_id):
        with self.connection() as db:
            row = db.execute("SELECT data FROM turn_requests WHERE id=?", (turn_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def requests(self, sid):
        with self.connection() as db:
            return [json.loads(r[0]) for r in db.execute(
                "SELECT data FROM turn_requests WHERE session_id=?", (sid,))]

    def save_request(self, turn):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO turn_requests VALUES (?,?,?)",
                       (turn["turn_id"], turn["session_id"], json.dumps(turn)))

    def publish(self, turn, result, content):
        session = self.get(turn["session_id"])
        if session["revision"] != turn["expected_revision"]:
            raise ValueError("Stale revision")
        session.update(revision=session["revision"] + 1,
                       head_checkpoint_id=result["result_checkpoint_id"], updated_at=now())
        if session["revision"] == 1 and not session["title_manual"]:
            session["title"] = " ".join(content.split())[:20]
        turn.update({k: v for k, v in result.items() if k != "text"})
        turn.update(status="completed", seq=session["revision"])
        with self.connection() as db:
            db.execute("UPDATE sessions SET data=? WHERE id=?", (json.dumps(session), session["id"]))
            db.execute("UPDATE turn_requests SET data=? WHERE id=?",
                       (json.dumps(turn), turn["turn_id"]))

"""Application directory and checkpoint references; graph owns all message/file bodies."""
import hashlib
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
            if version not in (0, 1, 2):
                raise ValueError("Unsupported catalog version")
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("""CREATE TABLE IF NOT EXISTS turn_requests
                (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id)
                 ON DELETE CASCADE, data TEXT NOT NULL)""")
            db.execute("CREATE TABLE IF NOT EXISTS run_inputs (id TEXT PRIMARY KEY REFERENCES turn_requests(id) ON DELETE CASCADE, content TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS run_events (run_id TEXT NOT NULL REFERENCES turn_requests(id) ON DELETE CASCADE, seq INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(run_id,seq))")
            db.execute("CREATE TABLE IF NOT EXISTS mutation_receipts (run_id TEXT NOT NULL REFERENCES turn_requests(id) ON DELETE CASCADE, call_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(run_id,call_id))")
            db.execute("PRAGMA user_version=2")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
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
        # Only initialize the head; never overwrite a concurrently renamed title.
        with self.connection() as db:
            row = json.loads(db.execute("SELECT data FROM sessions WHERE id=?", (session["id"],)).fetchone()[0])
            if row["head_checkpoint_id"] is None:
                row["head_checkpoint_id"] = session["head_checkpoint_id"]
                db.execute("UPDATE sessions SET data=? WHERE id=?", (json.dumps(row), row["id"]))

    def create(self):
        session = {"id": str(uuid4()), "title": "新会话", "title_manual": False,
                       "created_at": now(), "updated_at": now(), "revision": 0,
                       "head_checkpoint_id": None, "lifecycle": "active"}
        with self.connection() as db:
            db.execute("INSERT INTO sessions VALUES (?,?)", (session["id"], json.dumps(session)))
        return self.summary(session)

    def rename(self, sid, title):
        with self.connection() as db:
            row = db.execute("SELECT data FROM sessions WHERE id=?", (sid,)).fetchone()
            if not row:
                raise KeyError(sid)
            session = json.loads(row[0])
            if session["lifecycle"] != "active":
                raise KeyError(sid)
            session.update(title=title, title_manual=True, updated_at=now())
            db.execute("UPDATE sessions SET data=? WHERE id=?", (json.dumps(session), sid))
        return self.summary(session)

    def mark_deleting(self, sid):
        with self.connection() as db:
            row = db.execute("SELECT data FROM sessions WHERE id=?", (sid,)).fetchone()
            if not row:
                raise KeyError(sid)
            session = json.loads(row[0])
            session["lifecycle"] = "deleting"
            db.execute("UPDATE sessions SET data=? WHERE id=?", (json.dumps(session), sid))

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
        with self.connection() as db:
            session = json.loads(db.execute("SELECT data FROM sessions WHERE id=?", (turn["session_id"],)).fetchone()[0])
            if session["revision"] != turn["expected_revision"]:
                raise ValueError("Stale revision")
            session.update(revision=session["revision"] + 1,
                           head_checkpoint_id=result["result_checkpoint_id"], updated_at=now())
            if session["revision"] == 1 and not session["title_manual"]:
                session["title"] = " ".join(content.split())[:20]
            turn.update({k: v for k, v in result.items() if k != "text"})
            turn.update(status="completed", seq=session["revision"], updated_at=now())
            db.execute("UPDATE sessions SET data=? WHERE id=?", (json.dumps(session), session["id"]))
            db.execute("UPDATE turn_requests SET data=? WHERE id=?", (json.dumps(turn), turn["turn_id"]))
            db.execute("DELETE FROM run_inputs WHERE id=?", (turn["turn_id"],))

    def accept_run(self, sid, rid, revision, content, request_id=None):
        digest = hashlib.sha256(content.encode()).hexdigest()
        with self.connection() as db:
            old = db.execute("SELECT data FROM turn_requests WHERE id=?", (rid,)).fetchone()
            if old:
                data = json.loads(old[0])
                if (data["session_id"], data["expected_revision"], data["input_hash"]) != (sid, revision, digest):
                    raise ValueError("TURN_CONFLICT")
                return data
            row = db.execute("SELECT data FROM sessions WHERE id=?", (sid,)).fetchone()
            if not row or json.loads(row[0])["lifecycle"] != "active":
                raise KeyError(sid)
            session = json.loads(row[0])
            for item in db.execute("SELECT data FROM turn_requests WHERE session_id=?", (sid,)):
                if json.loads(item[0])["status"] in ("accepted", "running", "awaiting_approval", "interrupted", "needs_reconciliation"):
                    raise ValueError("RUN_ACTIVE")
            if revision != session["revision"]:
                raise ValueError("SESSION_CONFLICT")
            data = {"run_id": rid, "turn_id": rid, "session_id": sid, "expected_revision": revision,
                        "input_hash": digest, "base_checkpoint_id": session["head_checkpoint_id"],
                        "status": "accepted", "attempt_no": 1, "event_seq": 1, "spent": 0, "request_id": request_id or rid,
                        "created_at": now(), "updated_at": now(), "approvals": [], "checkpoint_id": None}
            db.execute("INSERT INTO turn_requests VALUES (?,?,?)", (rid, sid, json.dumps(data)))
            db.execute("INSERT INTO run_inputs VALUES (?,?)", (rid, content))
            event = {"seq": 1, "kind": "accepted", "label": "已接受请求", "at": now(), "path": None,
                         "run_id": rid, "turn_id": rid, "session_id": sid}
            db.execute("INSERT INTO run_events VALUES (?,?,?)", (rid, 1, json.dumps(event)))
            return data

    def input(self, rid):
        with self.connection() as db:
            row = db.execute("SELECT content FROM run_inputs WHERE id=?", (rid,)).fetchone()
        return row[0] if row else None

    def patch_run(self, rid, **fields):
        with self.connection() as db:
            row = db.execute("SELECT data FROM turn_requests WHERE id=?", (rid,)).fetchone()
            if not row:
                raise KeyError(rid)
            data = json.loads(row[0])
            data.update(fields, updated_at=now())
            db.execute("UPDATE turn_requests SET data=? WHERE id=?", (json.dumps(data), rid))
            if fields.get("input_checkpoint_id") or fields.get("status") == "abandoned":
                db.execute("DELETE FROM run_inputs WHERE id=?", (rid,))
            return data

    def event(self, rid, kind, label, path=None):
        with self.connection() as db:
            data = json.loads(db.execute("SELECT data FROM turn_requests WHERE id=?", (rid,)).fetchone()[0])
            seq = data.get("event_seq", 0) + 1
            event = {"seq": seq, "kind": kind, "label": label, "at": now(), "path": path,
                         "run_id": rid, "turn_id": rid, "session_id": data["session_id"]}
            data.update(event_seq=seq, updated_at=now())
            db.execute("UPDATE turn_requests SET data=? WHERE id=?", (json.dumps(data), rid))
            db.execute("INSERT INTO run_events VALUES (?,?,?)", (rid, seq, json.dumps(event)))
            db.execute("DELETE FROM run_events WHERE run_id=? AND seq<=?", (rid, seq-200))
            return event

    def events(self, rid, after):
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT data FROM run_events WHERE run_id=? AND seq>? ORDER BY seq LIMIT 200", (rid, after))]

    def receipts(self, rid):
        with self.connection() as db:
            return {row[0]: json.loads(row[1]) for row in db.execute(
                "SELECT call_id,data FROM mutation_receipts WHERE run_id=?", (rid,))}

    def receipt(self, rid, call_id, data):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO mutation_receipts VALUES (?,?,?)", (rid, call_id, json.dumps(data)))

    def reconcile_receipt(self, rid, call_id, version):
        with self.connection() as db:
            run = json.loads(db.execute("SELECT data FROM turn_requests WHERE id=?", (rid,)).fetchone()[0])
            receipts = {r[0]: json.loads(r[1]) for r in db.execute(
                "SELECT call_id,data FROM mutation_receipts WHERE run_id=?", (rid,))}
            receipt = receipts[call_id]
            if run['status'] != 'needs_reconciliation' or receipt['status'] not in ('executing', 'unknown'):
                raise ValueError('RECEIPT_STALE')
            receipt.update(status='reconciled', result_version=version, execution_confirmed=False)
            db.execute("UPDATE mutation_receipts SET data=? WHERE run_id=? AND call_id=?",
                       (json.dumps(receipt), rid, call_id))
            if not any(r['status'] in ('executing', 'unknown') for r in receipts.values()):
                run.update(status='interrupted', updated_at=now())
                db.execute("UPDATE turn_requests SET data=? WHERE id=?", (json.dumps(run), rid))

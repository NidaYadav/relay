"""SQLite store. One file, one connection per call, rows returned as dicts."""
import json
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RELAY_DATA_DIR", ROOT / "data"))
UPLOADS = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "relay.db"
SESSION_TTL_DAYS = 7

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    status TEXT NOT NULL,            -- reading | ready | failed
    mode TEXT NOT NULL,              -- ai | offline
    task_json TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS vault_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE COLLATE NOCASE,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    pages INTEGER NOT NULL,
    size INTEGER NOT NULL,
    content BLOB NOT NULL,
    added_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,              -- form | evidence
    filename TEXT NOT NULL,
    kind TEXT,
    pages INTEGER,
    text TEXT,
    path TEXT NOT NULL,
    meta_json TEXT
);
CREATE TABLE IF NOT EXISTS fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    ord INTEGER NOT NULL,
    section TEXT NOT NULL,
    key TEXT NOT NULL,
    label TEXT NOT NULL,
    plain_label TEXT,
    help TEXT,
    required INTEGER NOT NULL DEFAULT 1,
    answer_type TEXT NOT NULL DEFAULT 'text',
    options_json TEXT,
    source TEXT NOT NULL DEFAULT 'person',   -- person | documents | helper
    helper_reason TEXT,
    pdf_field TEXT,
    value TEXT,
    origin TEXT,                              -- user | documents | helper
    status TEXT NOT NULL DEFAULT 'open',      -- open | proposed | done | skipped | needs_helper | waiting
    evidence_json TEXT
);
CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    field_ids_json TEXT NOT NULL,
    question TEXT NOT NULL,
    items_json TEXT,                 -- [{"field_id": 1, "question": "..."}]
    note TEXT,
    crop_path TEXT,
    include_crop INTEGER NOT NULL DEFAULT 1,
    redactions_json TEXT,
    token TEXT UNIQUE,
    status TEXT NOT NULL,            -- draft | sent | answered | approved | rejected | cancelled
    answer_json TEXT,
    created_at REAL NOT NULL,
    expires_at REAL,
    answered_at REAL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    at REAL NOT NULL,
    agent TEXT NOT NULL,
    message TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info'
);
CREATE INDEX IF NOT EXISTS idx_fields_session ON fields(session_id, ord);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    UPLOADS.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.execute("PRAGMA journal_mode = WAL")
        c.executescript(SCHEMA)
        columns = {row["name"] for row in c.execute("PRAGMA table_info(handoffs)")}
        if "items_json" not in columns:
            c.execute("ALTER TABLE handoffs ADD COLUMN items_json TEXT")
    purge_old()


def purge_old():
    cutoff = time.time() - SESSION_TTL_DAYS * 86400
    with connect() as c:
        old = [r["id"] for r in c.execute("SELECT id FROM sessions WHERE created_at < ?", (cutoff,))]
    for sid in old:
        delete_session(sid)


def delete_session(sid: str):
    with connect() as c:
        c.execute("DELETE FROM sessions WHERE id = ?", (sid,))
    shutil.rmtree(UPLOADS / sid, ignore_errors=True)


def rows(sql, params=()):
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params)]


def row(sql, params=()):
    found = rows(sql, params)
    return found[0] if found else None


def execute(sql, params=()):
    with connect() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def update(table: str, rid, **values):
    cols = ", ".join(f"{k} = ?" for k in values)
    execute(f"UPDATE {table} SET {cols} WHERE id = ?", (*values.values(), rid))


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(text, default=None):
    if not text:
        return default
    return json.loads(text)

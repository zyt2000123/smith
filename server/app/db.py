import aiosqlite
from .config import SQLITE_PATH, ensure_dirs

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    device TEXT NOT NULL DEFAULT '',
    online INTEGER NOT NULL DEFAULT 1,
    description TEXT NOT NULL DEFAULT '',
    knowledge TEXT NOT NULL DEFAULT '[]',
    environment TEXT NOT NULL DEFAULT '本地',
    accent TEXT NOT NULL DEFAULT '',
    config_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('conversation', 'automation')),
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    session_id TEXT REFERENCES sessions(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        ensure_dirs()
        _db = await aiosqlite.connect(str(SQLITE_PATH))
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
        await _db.executescript(SCHEMA)
    return _db

async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None

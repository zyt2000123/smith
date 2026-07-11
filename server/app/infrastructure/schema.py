from __future__ import annotations

import aiosqlite


APP_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    device TEXT NOT NULL DEFAULT '',
    online INTEGER NOT NULL DEFAULT 1,
    description TEXT NOT NULL DEFAULT '',
    knowledge TEXT NOT NULL DEFAULT '[]',
    environment TEXT NOT NULL DEFAULT '',
    accent TEXT NOT NULL DEFAULT '',
    config_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agent_profiles(id) ON DELETE CASCADE,
    identity_id TEXT,
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
    agent_id TEXT NOT NULL REFERENCES agent_profiles(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('conversation', 'automation')),
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    session_id TEXT REFERENCES sessions(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auto_tasks (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agent_profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    trigger_type TEXT NOT NULL DEFAULT 'manual' CHECK (trigger_type IN ('manual', 'cron', 'interval')),
    trigger_config TEXT NOT NULL DEFAULT '',
    instruction TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'running', 'completed', 'failed')),
    last_run_at TEXT,
    next_run_at TEXT,
    run_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auto_task_runs (
    id TEXT PRIMARY KEY,
    auto_task_id TEXT NOT NULL REFERENCES auto_tasks(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    output TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    error TEXT
);

"""


async def _ensure_session_identity_column(db: aiosqlite.Connection) -> None:
    """Add the domain-identity binding to existing single-Smith sessions."""
    async with db.execute("PRAGMA table_info(sessions)") as cur:
        columns = {row[1] for row in await cur.fetchall()}
    if "identity_id" not in columns:
        await db.execute("ALTER TABLE sessions ADD COLUMN identity_id TEXT")


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.executescript(APP_SCHEMA)
    await _ensure_session_identity_column(db)
    await db.commit()

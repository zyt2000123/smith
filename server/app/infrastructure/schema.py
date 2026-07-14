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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(name, role)
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agent_profiles(id) ON DELETE CASCADE,
    identity_id TEXT,
    model_profile TEXT,
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    context_summary TEXT NOT NULL DEFAULT '',
    context_summary_cutoff INTEGER NOT NULL DEFAULT 0
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
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    lease_until TEXT,
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

CREATE TABLE IF NOT EXISTS token_usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    run_id TEXT,
    source_key TEXT,
    project_name TEXT NOT NULL DEFAULT '',
    project_path TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    total_tokens INTEGER NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    occurred_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_token_usage_session_time
    ON token_usage_events(session_id, occurred_at);

"""


async def _ensure_session_identity_column(db: aiosqlite.Connection) -> None:
    """Add the domain-identity binding to existing single-Smith sessions."""
    async with db.execute("PRAGMA table_info(sessions)") as cur:
        columns = {row[1] for row in await cur.fetchall()}
    if "identity_id" not in columns:
        await db.execute("ALTER TABLE sessions ADD COLUMN identity_id TEXT")


async def _ensure_session_context_columns(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA table_info(sessions)") as cur:
        columns = {row[1] for row in await cur.fetchall()}
    for name, definition in (
        ("model_profile", "TEXT"),
        ("context_summary", "TEXT NOT NULL DEFAULT ''"),
        ("context_summary_cutoff", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if name not in columns:
            await db.execute(f"ALTER TABLE sessions ADD COLUMN {name} {definition}")


async def _ensure_unique_profile_index(db: aiosqlite.Connection) -> None:
    """Add UNIQUE(name, role) to existing databases, deduplicating first."""
    await db.execute(
        "DELETE FROM agent_profiles WHERE rowid NOT IN "
        "(SELECT MIN(rowid) FROM agent_profiles GROUP BY name, role)"
    )
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_profiles_name_role "
        "ON agent_profiles(name, role)"
    )


async def _ensure_auto_task_columns(db: aiosqlite.Connection) -> None:
    """Migrate databases created before retry/lease fields existed."""
    async with db.execute("PRAGMA table_info(auto_tasks)") as cur:
        columns = {row[1] for row in await cur.fetchall()}
    for name, definition in (
        ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
        ("max_retries", "INTEGER NOT NULL DEFAULT 2"),
        ("lease_until", "TEXT"),
    ):
        if name not in columns:
            await db.execute(f"ALTER TABLE auto_tasks ADD COLUMN {name} {definition}")


async def _ensure_token_usage_columns(db: aiosqlite.Connection) -> None:
    """Add trace-import metadata to databases created before /token existed."""
    async with db.execute("PRAGMA table_info(token_usage_events)") as cur:
        columns = {row[1] for row in await cur.fetchall()}
    if "source_key" not in columns:
        await db.execute("ALTER TABLE token_usage_events ADD COLUMN source_key TEXT")
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_token_usage_source_key "
        "ON token_usage_events(source_key) WHERE source_key IS NOT NULL"
    )


async def _reset_stuck_auto_tasks(db: aiosqlite.Connection) -> None:
    """Reset tasks stuck at 'running' from a prior crash."""
    await db.execute(
        "UPDATE auto_tasks SET status='idle', lease_until=NULL WHERE status='running'"
    )
    await db.execute(
        "UPDATE auto_task_runs SET status='failed', error='interrupted by restart', "
        "finished_at=datetime('now') WHERE status='running'"
    )


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.executescript(APP_SCHEMA)
    await _ensure_session_identity_column(db)
    await _ensure_session_context_columns(db)
    await _ensure_unique_profile_index(db)
    await _ensure_auto_task_columns(db)
    await _ensure_token_usage_columns(db)
    await _reset_stuck_auto_tasks(db)
    await db.commit()

from __future__ import annotations

import sys
from pathlib import Path

import aiosqlite
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.schema import ensure_schema  # noqa: E402


@pytest.mark.asyncio
async def test_schema_adds_identity_binding_to_existing_sessions() -> None:
    db = await aiosqlite.connect(":memory:")
    try:
        await db.executescript(
            """
CREATE TABLE agent_profiles (id TEXT PRIMARY KEY);
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
        )

        await ensure_schema(db)

        async with db.execute("PRAGMA table_info(sessions)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        assert "identity_id" in columns
    finally:
        await db.close()

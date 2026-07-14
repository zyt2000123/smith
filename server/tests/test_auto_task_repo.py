from __future__ import annotations

from datetime import datetime, timezone
import importlib

import aiosqlite
import pytest

from app.infrastructure import schema as schema_module
from app.infrastructure.repositories.auto_task_repo import AutoTaskRepo


@pytest.mark.asyncio
async def test_auto_task_schema_migrates_retry_and_lease_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.executescript(
        """
        CREATE TABLE auto_tasks (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            trigger_type TEXT NOT NULL DEFAULT 'manual',
            trigger_config TEXT NOT NULL DEFAULT '',
            instruction TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'idle',
            last_run_at TEXT,
            next_run_at TEXT,
            run_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """
    )

    await schema_module.ensure_schema(db)
    async with db.execute("PRAGMA table_info(auto_tasks)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}

    assert {"retry_count", "max_retries", "lease_until"} <= columns
    await db.close()


@pytest.mark.asyncio
async def test_auto_task_claim_uses_a_lease_to_prevent_duplicate_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await schema_module.ensure_schema(db)
    repo_module = importlib.import_module("app.infrastructure.repositories.auto_task_repo")

    async def fake_get_app_db():
        return db

    monkeypatch.setitem(repo_module.AutoTaskRepo.create.__globals__, "get_app_db", fake_get_app_db)
    repo = AutoTaskRepo()
    await repo.create(
        "smith",
        {
            "title": "probe",
            "instruction": "check",
            "trigger_type": "interval",
            "trigger_config": "60",
            "next_run_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    task = (await repo.list_by_agent("smith"))[0]

    assert await repo.claim_running(task["id"]) is True
    assert await repo.claim_running(task["id"]) is False
    claimed = await repo.get(task["id"])
    assert claimed is not None
    assert claimed["lease_until"] is not None

    await db.close()

from __future__ import annotations

import aiosqlite
import pytest
import pytest_asyncio

from engine.llm.observability import GenerationRecord
from app.services.token_stats_service import TokenStatsService


@pytest_asyncio.fixture(autouse=True)
async def close_test_connections(monkeypatch: pytest.MonkeyPatch):
    connections: list[aiosqlite.Connection] = []
    connect = aiosqlite.connect

    async def tracked_connect(*args, **kwargs) -> aiosqlite.Connection:
        connection = await connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(aiosqlite, "connect", tracked_connect)
    yield
    for connection in connections:
        await connection.close()


_GENERATIONS_DDL = """
CREATE TABLE llm_generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT,
    session_id TEXT,
    run_id TEXT,
    purpose TEXT NOT NULL DEFAULT 'other',
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    ttft_ms INTEGER,
    total_ms INTEGER NOT NULL DEFAULT 0,
    stream INTEGER NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL DEFAULT 1,
    occurred_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX uq_llm_generations_source_key
    ON llm_generations(source_key) WHERE source_key IS NOT NULL;
"""


async def _service() -> tuple[TokenStatsService, aiosqlite.Connection]:
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.executescript(_GENERATIONS_DDL)

    async def provider() -> aiosqlite.Connection:
        return db

    return TokenStatsService(provider), db


def _record(**overrides: object) -> GenerationRecord:
    defaults: dict = {
        "provider": "openai",
        "model": "deepseek-v4-pro",
        "purpose": "main",
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 200,
            "total_tokens": 1200,
            "cache_read_tokens": 600,
            "cache_write_tokens": 0,
            "reasoning_tokens": 50,
        },
        "ttft_ms": 120,
        "total_ms": 900,
        "stream": True,
        "ok": True,
        "run_id": "r1",
        "session_id": "s1",
        "occurred_at": "2026-07-22T08:00:00+00:00",
    }
    defaults.update(overrides)
    return GenerationRecord(**defaults)


@pytest.mark.asyncio
async def test_record_generation_persists_all_fields() -> None:
    service, db = await _service()
    await service.record_generation(_record())

    rows = await db.execute_fetchall("SELECT * FROM llm_generations")
    assert len(rows) == 1
    row = rows[0]
    assert row["model"] == "deepseek-v4-pro"
    assert row["purpose"] == "main"
    assert row["cache_read_tokens"] == 600
    assert row["reasoning_tokens"] == 50
    assert row["ttft_ms"] == 120
    assert row["stream"] == 1
    assert row["ok"] == 1
    assert row["run_id"] == "r1"


@pytest.mark.asyncio
async def test_record_generation_deduplicates_by_source_key() -> None:
    service, db = await _service()
    record = _record()
    await service.record_generation(record)
    await service.record_generation(record)

    rows = await db.execute_fetchall("SELECT COUNT(*) AS n FROM llm_generations")
    assert rows[0]["n"] == 1


@pytest.mark.asyncio
async def test_generation_stats_aggregates_by_model_and_purpose() -> None:
    service, _ = await _service()
    await service.record_generation(_record())
    await service.record_generation(_record(purpose="memory", ok=False, ttft_ms=None))
    await service.record_generation(_record(model="gpt-5.2", purpose="gate"))

    stats = await service.get_generation_stats(year=2026)
    groups = {(g["model"], g["purpose"]): g for g in stats["groups"]}
    assert ("deepseek-v4-pro", "main") in groups
    assert ("deepseek-v4-pro", "memory") in groups
    assert ("gpt-5.2", "gate") in groups
    main_group = groups[("deepseek-v4-pro", "main")]
    assert main_group["calls"] == 1
    assert main_group["cache_read_tokens"] == 600
    assert groups[("deepseek-v4-pro", "memory")]["failed_calls"] == 1


@pytest.mark.asyncio
async def test_generation_stats_costs_use_price_table(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _ = await _service()
    await service.record_generation(_record())

    monkeypatch.setattr(
        TokenStatsService,
        "_load_price_table",
        staticmethod(lambda: {
            "deepseek-v4-pro": {
                "input": 1.0,
                "output": 4.0,
                "cache_read": 0.1,
            },
        }),
    )
    stats = await service.get_generation_stats(year=2026)
    group = stats["groups"][0]
    # (1000-600)*1.0 + 600*0.1 + 200*4.0 = 400 + 60 + 800 = 1260 per 1M
    assert group["cost"] == pytest.approx(0.00126)
    assert stats["total_cost"] == pytest.approx(0.00126)


@pytest.mark.asyncio
async def test_generation_stats_without_price_table_reports_no_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = await _service()
    await service.record_generation(_record())
    monkeypatch.setattr(TokenStatsService, "_load_price_table", staticmethod(dict))

    stats = await service.get_generation_stats(year=2026)
    assert stats["groups"][0]["cost"] is None
    assert stats["total_cost"] is None

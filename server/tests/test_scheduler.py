from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import scheduler as scheduler_module  # noqa: E402


@pytest.mark.asyncio
async def test_scheduler_runs_memory_maintenance_after_auto_task_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeAutoTaskService:
        async def tick(self) -> int:
            calls.append("tasks")
            return 0

    async def fake_memory_tick() -> bool:
        calls.append("memory")
        return True

    monkeypatch.setattr(scheduler_module, "_build_service", lambda: FakeAutoTaskService())
    monkeypatch.setattr(scheduler_module, "run_memory_maintenance_tick", fake_memory_tick)

    await scheduler_module.run_scheduler_tick()

    assert calls == ["tasks", "memory"]

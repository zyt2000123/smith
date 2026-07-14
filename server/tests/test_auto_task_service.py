from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import auto_task_service as auto_task_service_module  # noqa: E402
from app.services.auto_task_service import AutoTaskService  # noqa: E402


class FakeAutoTaskRepo:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    async def claim_running(self, task_id: str) -> bool:
        return True

    async def finish_task(self, task_id: str, status: str, next_run_at: str | None) -> None:
        self.updates.append({"task_id": task_id, "status": status, "next_run_at": next_run_at})

    async def update(self, task_id: str, updates: dict):
        self.updates.append(dict(updates))

    async def create_run(self, task_id: str) -> dict:
        return {
            "id": "run-1",
            "auto_task_id": task_id,
            "status": "running",
            "output": "",
            "started_at": "2026-07-11T00:00:00Z",
            "finished_at": None,
            "error": None,
        }

    async def finish_run(self, run_id: str, status: str, output: str, error: str | None = None) -> dict:
        return {
            "id": run_id,
            "auto_task_id": "task-1",
            "status": status,
            "output": output,
            "started_at": "2026-07-11T00:00:00Z",
            "finished_at": "2026-07-11T00:01:00Z",
            "error": error,
        }


class FakeProfileRepo:
    async def get(self, agent_id: str) -> dict:
        return {"id": agent_id, "name": "Smith"}


class FakeSessionRepo:
    def __init__(self) -> None:
        self.created: list[tuple[str, str, str | None]] = []
        self.messages: list[tuple[str, str, str]] = []

    async def create(self, agent_id: str, title: str, identity_id: str | None = None) -> dict:
        self.created.append((agent_id, title, identity_id))
        return {"id": "session-1", "agent_id": agent_id, "identity_id": identity_id}

    async def add_message(self, session_id: str, role: str, content: str) -> dict:
        self.messages.append((session_id, role, content))
        return {"id": f"{role}-1", "session_id": session_id, "role": role, "content": content}


@pytest.mark.asyncio
async def test_auto_task_pins_its_generated_session_to_the_resolved_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Catalog:
        def resolve(self, message: str):
            assert message == "审查这份合同"
            return SimpleNamespace(identity_id="legal")

    def fake_build_runtime(agent_id: str, name: str, *, session_id: str | None = None):
        captured["runtime"] = (agent_id, name, session_id)
        return object(), object()

    async def fake_reply(request, runtime, services):
        captured["request"] = request
        return SimpleNamespace(text="合同审查完成")

    monkeypatch.setattr(auto_task_service_module, "load_runtime_identity_catalog", lambda: Catalog())
    monkeypatch.setattr(auto_task_service_module, "build_engine_runtime", fake_build_runtime)
    monkeypatch.setattr(auto_task_service_module, "engine_reply_with_runtime", fake_reply)

    task_repo = FakeAutoTaskRepo()
    session_repo = FakeSessionRepo()
    service = AutoTaskService(task_repo, FakeProfileRepo(), session_repo)
    task = {
        "id": "task-1",
        "agent_id": "smith-id",
        "title": "合同检查",
        "instruction": "审查这份合同",
        "trigger_type": "manual",
        "trigger_config": "",
        "run_count": 0,
    }

    result = await service.run_auto_task(task)

    assert result.status == "completed"
    assert session_repo.created == [("smith-id", "[自动] 合同检查", "legal")]
    assert captured["request"].identity_id == "legal"


@pytest.mark.asyncio
async def test_failed_scheduled_auto_task_is_requeued_with_retry_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Catalog:
        def resolve(self, message: str):
            return SimpleNamespace(identity_id="smith")

    async def fail_reply(request, runtime, services):
        raise RuntimeError("temporary provider outage")

    monkeypatch.setattr(auto_task_service_module, "load_runtime_identity_catalog", lambda: Catalog())
    monkeypatch.setattr(auto_task_service_module, "build_engine_runtime", lambda *args, **kwargs: (object(), object()))
    monkeypatch.setattr(auto_task_service_module, "engine_reply_with_runtime", fail_reply)

    task_repo = FakeAutoTaskRepo()
    service = AutoTaskService(task_repo, FakeProfileRepo(), FakeSessionRepo())
    task = {
        "id": "task-1",
        "agent_id": "smith-id",
        "title": "定时检查",
        "instruction": "检查服务",
        "trigger_type": "interval",
        "trigger_config": "3600",
        "run_count": 0,
        "retry_count": 0,
        "max_retries": 2,
    }

    result = await service.run_auto_task(task)

    assert result.status == "failed"
    assert any(update.get("retry_count") == 1 for update in task_repo.updates)
    retry_update = next(update for update in task_repo.updates if "retry_count" in update)
    assert retry_update["retry_count"] == 1
    task_update = next(update for update in task_repo.updates if update.get("task_id") == "task-1")
    assert task_update["status"] == "idle"
    assert task_update["next_run_at"] is not None


@pytest.mark.asyncio
async def test_exhausted_retry_chain_resets_before_next_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_reply(request, runtime, services):
        raise RuntimeError("persistent provider outage")

    monkeypatch.setattr(
        auto_task_service_module,
        "load_runtime_identity_catalog",
        lambda: SimpleNamespace(resolve=lambda message: SimpleNamespace(identity_id="smith")),
    )
    monkeypatch.setattr(
        auto_task_service_module,
        "build_engine_runtime",
        lambda *args, **kwargs: (object(), object()),
    )
    monkeypatch.setattr(auto_task_service_module, "engine_reply_with_runtime", fail_reply)

    task_repo = FakeAutoTaskRepo()
    service = AutoTaskService(task_repo, FakeProfileRepo(), FakeSessionRepo())
    task = {
        "id": "task-1",
        "agent_id": "smith-id",
        "title": "定时检查",
        "instruction": "检查服务",
        "trigger_type": "interval",
        "trigger_config": "3600",
        "retry_count": 2,
        "max_retries": 2,
    }

    result = await service.run_auto_task(task)

    assert result.status == "failed"
    assert {"retry_count": 0} in task_repo.updates

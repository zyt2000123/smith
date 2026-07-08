from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import session_service as session_service_module
from app.services.session_service import SessionService


class FakeSessionRepo:
    def __init__(self) -> None:
        self.saved_messages: list[tuple[str, str, str]] = []

    async def exists(self, session_id: str, employee_id: str) -> bool:
        return True

    async def get_messages(self, session_id: str, limit: int = 0, offset: int = 0) -> list[dict]:
        return []

    async def add_message(self, session_id: str, role: str, content: str) -> dict:
        self.saved_messages.append((session_id, role, content))
        return {
            "id": f"{role}-1",
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": "2026-07-07T00:00:00Z",
        }


class FakeEmployeeRepo:
    async def get(self, employee_id: str) -> dict | None:
        return {"id": employee_id, "name": "Smith"}


@pytest.mark.asyncio
async def test_stream_message_forwards_skill_name_and_blocked_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str | None] = {}

    async def fake_engine_reply_events(
        employee_id: str,
        name: str,
        content: str,
        history=None,
        context: str | None = None,
        forced_skill: str | None = None,
    ):
        captured["forced_skill"] = forced_skill
        yield SimpleNamespace(type=SimpleNamespace(value="tool_call_result"), data={
            "id": "tool-1",
            "blocked": True,
            "reason": "permission denied",
        })
        yield SimpleNamespace(type=SimpleNamespace(value="text_delta"), data={"text": "done"})

    monkeypatch.setattr(session_service_module, "engine_reply_events", fake_engine_reply_events)

    svc = SessionService(FakeSessionRepo(), FakeEmployeeRepo())
    events = [
        event
        async for event in svc.stream_message(
            "emp-1",
            "sess-1",
            "analyze this repo",
            skill_name="planning",
        )
    ]

    assert captured["forced_skill"] == "planning"
    tool_event = next(event for event in events if event["event"] == "tool_result")
    payload = json.loads(tool_event["data"])
    assert payload["blocked"] is True
    assert payload["error"] is True
    assert payload["summary"] == "permission denied"

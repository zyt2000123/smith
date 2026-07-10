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

    async def exists(self, session_id: str, agent_id: str) -> bool:
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


class FakeAgentProfileRepo:
    async def get(self, agent_id: str) -> dict | None:
        return {"id": agent_id, "name": "Smith"}


@pytest.mark.asyncio
async def test_stream_message_forwards_skill_name_and_blocked_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_build_engine_runtime(agent_id: str, name: str, *, session_id: str | None = None):
        return SimpleNamespace(agent_id=agent_id, agent_name=name, session_id=session_id), object()

    async def fake_engine_reply_events(request, runtime, services):
        captured["forced_skill"] = request.forced_skill
        captured["session_id"] = runtime.session_id
        yield SimpleNamespace(type=SimpleNamespace(value="tool_call_result"), data={
            "id": "tool-1",
            "blocked": True,
            "reason": "permission denied",
        })
        yield SimpleNamespace(type=SimpleNamespace(value="tool_call_result"), data={
            "id": "tool-2",
            "preflight": True,
            "blocked": False,
            "error": False,
            "reason": "present facts and retry",
        })
        yield SimpleNamespace(type=SimpleNamespace(value="text_delta"), data={"text": "done"})

    monkeypatch.setattr(session_service_module, "build_engine_runtime", fake_build_engine_runtime)
    monkeypatch.setattr(
        session_service_module,
        "engine_reply_events_with_runtime",
        fake_engine_reply_events,
    )

    svc = SessionService(FakeSessionRepo(), FakeAgentProfileRepo())
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
    assert captured["session_id"] == "sess-1"
    tool_events = [event for event in events if event["event"] == "tool_result"]
    blocked_payload = json.loads(tool_events[0]["data"])
    assert blocked_payload["blocked"] is True
    assert blocked_payload["preflight"] is False
    assert blocked_payload["error"] is True
    assert blocked_payload["summary"] == "permission denied"

    preflight_payload = json.loads(tool_events[1]["data"])
    assert preflight_payload["preflight"] is True
    assert preflight_payload["blocked"] is False
    assert preflight_payload["error"] is False
    assert preflight_payload["summary"] == "present facts and retry"


@pytest.mark.asyncio
async def test_stream_message_saves_partial_reply_on_client_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_build_engine_runtime(agent_id: str, name: str, *, session_id: str | None = None):
        return SimpleNamespace(agent_id=agent_id, agent_name=name, session_id=session_id), object()

    async def fake_engine_reply_events(request, runtime, services):
        yield SimpleNamespace(type=SimpleNamespace(value="text_delta"), data={"text": "partial "})
        yield SimpleNamespace(type=SimpleNamespace(value="text_delta"), data={"text": "reply"})
        yield SimpleNamespace(type=SimpleNamespace(value="text_delta"), data={"text": " never sent"})

    monkeypatch.setattr(session_service_module, "build_engine_runtime", fake_build_engine_runtime)
    monkeypatch.setattr(
        session_service_module,
        "engine_reply_events_with_runtime",
        fake_engine_reply_events,
    )

    repo = FakeSessionRepo()
    svc = SessionService(repo, FakeAgentProfileRepo())
    stream = svc.stream_message("emp-1", "sess-1", "hello")
    await anext(stream)
    await anext(stream)
    # 模拟客户端断连：SSE 响应会 aclose 生成器，触发 GeneratorExit
    await stream.aclose()

    assert ("sess-1", "assistant", "partial reply") in repo.saved_messages

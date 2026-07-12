from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import session_service as session_service_module
from app.services.session_service import SessionService
from engine.identity_catalog import IdentityCatalog


class FakeSessionRepo:
    def __init__(self) -> None:
        self.saved_messages: list[tuple[str, str, str]] = []
        self.identity_id: str | None = None

    async def exists(self, session_id: str, agent_id: str) -> bool:
        return True

    async def get_owned(self, session_id: str, agent_id: str) -> dict | None:
        return {
            "id": session_id,
            "agent_id": agent_id,
            "identity_id": self.identity_id,
            "title": "Test session",
            "created_at": "2026-07-07T00:00:00Z",
        }

    async def claim_identity(self, session_id: str, agent_id: str, identity_id: str) -> bool:
        if self.identity_id is not None:
            return False
        self.identity_id = identity_id
        return True

    async def get_messages(self, session_id: str, limit: int = 0, offset: int = 0) -> list[dict]:
        return []

    async def get_recent_messages(self, session_id: str, limit: int) -> list[dict]:
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


def _identity_catalog(tmp_path: Path) -> IdentityCatalog:
    (tmp_path / "smith.yaml").write_text(
        """
schema: agentsmith.identity/v1
id: smith
name: Smith
default: true
routes: []
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "legal.yaml").write_text(
        """
schema: agentsmith.identity/v1
id: legal
name: \u6cd5\u52a1\u52a9\u624b
routes:
  - id: contract_review
    keywords: [\u5408\u540c]
    pipeline: legal-contract-review
""".strip(),
        encoding="utf-8",
    )
    return IdentityCatalog.load(tmp_path)


class FakeRun:
    def __init__(self, events) -> None:
        self._events = events

    async def stream_events(self):
        async for event in self._events:
            yield event


def _fake_run(factory):
    def build(request, runtime, services):
        return FakeRun(factory(request, runtime, services))

    return build


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
        "engine_run_stream_with_runtime",
        _fake_run(fake_engine_reply_events),
    )

    svc = SessionService(FakeSessionRepo(), FakeAgentProfileRepo())
    events = [
        event
        async for event in svc.stream_message(
            "smith-id",
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
async def test_first_message_auto_selects_and_pins_identity(tmp_path: Path) -> None:
    repo = FakeSessionRepo()
    service = SessionService(
        repo,
        FakeAgentProfileRepo(),
        identity_catalog=_identity_catalog(tmp_path),
    )

    selected = await service._resolve_session_identity(
        "smith-id",
        "sess-1",
        "请审查这份合同",
        None,
    )
    follow_up = await service._resolve_session_identity(
        "smith-id",
        "sess-1",
        "顺便帮我整理一下措辞",
        None,
    )

    assert selected == "legal"
    assert follow_up == "legal"
    assert repo.identity_id == "legal"


@pytest.mark.asyncio
async def test_session_rejects_switching_a_pinned_identity(tmp_path: Path) -> None:
    repo = FakeSessionRepo()
    repo.identity_id = "legal"
    service = SessionService(
        repo,
        FakeAgentProfileRepo(),
        identity_catalog=_identity_catalog(tmp_path),
    )

    with pytest.raises(HTTPException) as exc:
        await service._resolve_session_identity(
            "smith-id",
            "sess-1",
            "hello",
            "smith",
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_stream_message_forwards_provider_text_delta_without_replaying_final_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_build_engine_runtime(agent_id: str, name: str, *, session_id: str | None = None):
        return SimpleNamespace(agent_id=agent_id, agent_name=name, session_id=session_id), object()

    async def fake_engine_reply_events(request, runtime, services):
        yield SimpleNamespace(
            type=SimpleNamespace(value="raw_response_event"),
            data={
                "type": "response.output_text.delta",
                "data": {"delta": "live reply"},
            },
        )
        yield SimpleNamespace(
            type=SimpleNamespace(value="text_delta"),
            data={"text": "live reply", "already_streamed": True},
        )
        yield SimpleNamespace(
            type=SimpleNamespace(value="run_finished"),
            data={"run_id": "run-1", "status": "completed"},
        )

    monkeypatch.setattr(session_service_module, "build_engine_runtime", fake_build_engine_runtime)
    monkeypatch.setattr(
        session_service_module,
        "engine_run_stream_with_runtime",
        _fake_run(fake_engine_reply_events),
    )

    repo = FakeSessionRepo()
    events = [
        event
        async for event in SessionService(repo, FakeAgentProfileRepo()).stream_message(
            "smith-id",
            "sess-1",
            "hello",
        )
    ]

    message_events = [event for event in events if event["event"] == "message"]
    assert [json.loads(event["data"])["text"] for event in message_events] == ["live reply"]
    assert ("sess-1", "assistant", "live reply") in repo.saved_messages
    assert json.loads(events[-1]["data"])["status"] == "completed"


@pytest.mark.asyncio
async def test_stream_message_forwards_provisional_lifecycle_and_persists_only_committed_final_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_build_engine_runtime(agent_id: str, name: str, *, session_id: str | None = None):
        return SimpleNamespace(agent_id=agent_id, agent_name=name, session_id=session_id), object()

    async def fake_engine_reply_events(request, runtime, services):
        yield SimpleNamespace(
            type=SimpleNamespace(value="raw_response_event"),
            data={
                "type": "response.output_text.delta",
                "data": {"delta": "discard me"},
                "provision_id": "draft-1",
            },
        )
        yield SimpleNamespace(
            type=SimpleNamespace(value="provisional_text_delta"),
            data={"provision_id": "draft-1", "text": "discard me"},
        )
        yield SimpleNamespace(
            type=SimpleNamespace(value="provisional_retract"),
            data={"provision_id": "draft-1", "reason": "incomplete_final_repair"},
        )
        yield SimpleNamespace(
            type=SimpleNamespace(value="provisional_text_delta"),
            data={"provision_id": "draft-2", "text": "final answer"},
        )
        yield SimpleNamespace(
            type=SimpleNamespace(value="provisional_commit"),
            data={"provision_id": "draft-2"},
        )
        yield SimpleNamespace(
            type=SimpleNamespace(value="text_delta"),
            data={"text": "final answer", "already_streamed": True},
        )
        yield SimpleNamespace(
            type=SimpleNamespace(value="run_finished"),
            data={"run_id": "run-1", "status": "completed"},
        )

    monkeypatch.setattr(session_service_module, "build_engine_runtime", fake_build_engine_runtime)
    monkeypatch.setattr(
        session_service_module,
        "engine_run_stream_with_runtime",
        _fake_run(fake_engine_reply_events),
    )

    repo = FakeSessionRepo()
    events = [
        event
        async for event in SessionService(repo, FakeAgentProfileRepo()).stream_message(
            "smith-id",
            "sess-1",
            "hello",
        )
    ]

    lifecycle = [event for event in events if event["event"].startswith("provisional")]
    assert [event["event"] for event in lifecycle] == [
        "provisional_text_delta",
        "provisional_retract",
        "provisional_text_delta",
        "provisional_commit",
    ]
    assert [json.loads(event["data"]) for event in lifecycle] == [
        {"provision_id": "draft-1", "text": "discard me"},
        {"provision_id": "draft-1", "reason": "incomplete_final_repair"},
        {"provision_id": "draft-2", "text": "final answer"},
        {"provision_id": "draft-2"},
    ]
    assert not [event for event in events if event["event"] == "message"]
    assert ("sess-1", "assistant", "final answer") in repo.saved_messages


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
        "engine_run_stream_with_runtime",
        _fake_run(fake_engine_reply_events),
    )

    repo = FakeSessionRepo()
    svc = SessionService(repo, FakeAgentProfileRepo())
    stream = svc.stream_message("smith-id", "sess-1", "hello")
    await anext(stream)
    await anext(stream)
    # 模拟客户端断连：SSE 响应会 aclose 生成器，触发 GeneratorExit
    await stream.aclose()

    assert ("sess-1", "assistant", "partial reply") in repo.saved_messages


@pytest.mark.asyncio
async def test_stream_message_marks_model_output_limit_as_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_build_engine_runtime(agent_id: str, name: str, *, session_id: str | None = None):
        return SimpleNamespace(agent_id=agent_id, agent_name=name, session_id=session_id), object()

    async def fake_engine_reply_events(request, runtime, services):
        yield SimpleNamespace(type=SimpleNamespace(value="text_delta"), data={"text": "partial answer"})
        yield SimpleNamespace(
            type=SimpleNamespace(value="incomplete"),
            data={"reason": "model_output_limit", "continuations": 2},
        )
        yield SimpleNamespace(type=SimpleNamespace(value="done"), data={})

    monkeypatch.setattr(session_service_module, "build_engine_runtime", fake_build_engine_runtime)
    monkeypatch.setattr(
        session_service_module,
        "engine_run_stream_with_runtime",
        _fake_run(fake_engine_reply_events),
    )

    events = [
        event
        async for event in SessionService(FakeSessionRepo(), FakeAgentProfileRepo()).stream_message(
            "smith-id",
            "sess-1",
            "hello",
        )
    ]

    done = json.loads(events[-1]["data"])
    assert done == {"id": "assistant-1", "status": "incomplete"}


@pytest.mark.asyncio
async def test_stream_message_marks_unhandled_engine_error_as_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_build_engine_runtime(agent_id: str, name: str, *, session_id: str | None = None):
        return SimpleNamespace(agent_id=agent_id, agent_name=name, session_id=session_id), object()

    async def fake_engine_reply_events(request, runtime, services):
        if False:
            yield None
        raise RuntimeError("unexpected engine failure")

    monkeypatch.setattr(session_service_module, "build_engine_runtime", fake_build_engine_runtime)
    monkeypatch.setattr(
        session_service_module,
        "engine_run_stream_with_runtime",
        _fake_run(fake_engine_reply_events),
    )

    events = [
        event
        async for event in SessionService(FakeSessionRepo(), FakeAgentProfileRepo()).stream_message(
            "smith-id",
            "sess-1",
            "hello",
        )
    ]

    assert any(event["event"] == "message" for event in events)
    done = json.loads(events[-1]["data"])
    assert done == {"id": None, "status": "failed"}

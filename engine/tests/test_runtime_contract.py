from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from engine.execution import agent_loop as agent_loop_module
from engine.execution.agent_loop import (
    reply_events_with_runtime,
    reply_with_runtime,
    run_stream_with_runtime,
)
from engine.execution.events import EventType
from engine.execution.runtime import EngineRequest, RuntimeContext, RuntimeServices
from engine.llm.client import ChatResponse, ToolCallData
from engine.skill.registry import SkillRegistry
from engine.tool.registry import ToolRegistry


class FakeLLM:
    def __init__(self) -> None:
        self.closed = False
        self.messages: list[dict] = []

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        prefix_cache_key: str | None = None,
    ) -> ChatResponse:
        self.messages = messages
        return ChatResponse(text="runtime reply")

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ):
        self.messages = messages
        yield "streamed reply"

    async def close(self) -> None:
        self.closed = True


class ToolCallingLLM(FakeLLM):
    def __init__(self) -> None:
        super().__init__()
        self.responses = [
            ChatResponse(tool_calls=[ToolCallData(id="call-1", name="unknown_tool", arguments={})]),
            ChatResponse(text="tool-assisted reply"),
        ]

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        prefix_cache_key: str | None = None,
    ) -> ChatResponse:
        self.messages = messages
        return self.responses.pop(0)


def _write_profile(profile_dir: Path) -> None:
    profile_dir.mkdir(parents=True)
    for filename, content in {
        "role.md": "You are Smith.",
        "style.md": "Be clear.",
        "workflow.md": "Pick skills only when needed.",
        "toolbox.md": "Use tools deliberately.",
        "context.md": "Remember the user's preferences.",
        "config.yaml": "tools:\n  enabled: []\n",
    }.items():
        (profile_dir / filename).write_text(content, encoding="utf-8")


def _runtime(tmp_path: Path) -> tuple[RuntimeContext, RuntimeServices, FakeLLM]:
    profile_dir = tmp_path / "profile"
    agents_dir = tmp_path / "agents"
    _write_profile(profile_dir)
    (agents_dir / "tools").mkdir(parents=True)
    (agents_dir / "skills").mkdir(parents=True)
    llm = FakeLLM()
    runtime = RuntimeContext(
        agent_id="smith",
        agent_name="Smith",
        profile_dir=profile_dir,
        agents_dir=agents_dir,
        session_id="sess-1",
    )
    services = RuntimeServices(
        llm=llm,  # type: ignore[arg-type]
        tool_registry=ToolRegistry(),
        skill_registry=SkillRegistry(),
    )
    return runtime, services, llm


def test_reply_with_runtime_uses_explicit_profile_context(tmp_path: Path) -> None:
    async def run() -> FakeLLM:
        runtime, services, llm = _runtime(tmp_path)
        result = await reply_with_runtime(
            EngineRequest(message="hello", context="cwd=/tmp/work"),
            runtime,
            services,
        )

        assert result.text == "runtime reply"
        assert result.had_tools is False
        assert not (runtime.profile_dir / "memory" / "recent.jsonl").exists()
        return llm

    llm = asyncio.run(run())
    assert llm.closed is True
    assert llm.messages[-1]["content"] == "hello\n\ncwd=/tmp/work"
    assert "agent_id: smith" in llm.messages[0]["content"]
    assert "_profile_dir:" in llm.messages[0]["content"]


def test_reply_with_runtime_marks_actual_tool_activity(tmp_path: Path) -> None:
    async def run() -> ToolCallingLLM:
        runtime, services, _ = _runtime(tmp_path)
        llm = ToolCallingLLM()
        services.llm = llm  # type: ignore[assignment]

        result = await reply_with_runtime(EngineRequest(message="use a tool"), runtime, services)

        assert result.text == "tool-assisted reply"
        assert result.had_tools is True
        assert (runtime.profile_dir / "memory" / "recent.jsonl").is_file()
        return llm

    llm = asyncio.run(run())
    assert llm.closed is True


def test_reply_events_with_runtime_emits_decision_reply_and_closes(tmp_path: Path) -> None:
    async def run() -> tuple[list[str], FakeLLM]:
        runtime, services, llm = _runtime(tmp_path)
        chunks: list[str] = []
        async for event in reply_events_with_runtime(
            EngineRequest(message="hello"),
            runtime,
            services,
        ):
            if event.type == EventType.TEXT_DELTA:
                chunks.append(event.data["text"])
        return chunks, llm

    chunks, llm = asyncio.run(run())
    assert chunks == ["runtime reply"]
    assert llm.closed is True


def test_runtime_services_close_closes_the_gate_client(tmp_path: Path) -> None:
    runtime, services, llm = _runtime(tmp_path)
    gate_llm = FakeLLM()
    services.gate_llm = gate_llm  # type: ignore[assignment]

    asyncio.run(services.close())

    assert runtime.agent_id == "smith"
    assert llm.closed is True
    assert gate_llm.closed is True


def test_run_stream_reports_terminal_state_only_after_it_is_drained(tmp_path: Path) -> None:
    async def run():
        runtime, services, _ = _runtime(tmp_path)
        stream = run_stream_with_runtime(EngineRequest(message="hello"), runtime, services)
        assert stream.is_complete is False
        events = [event async for event in stream.stream_events()]
        return stream, events

    stream, events = asyncio.run(run())

    assert events[0].type == EventType.RUN_STARTED
    assert events[-1].type == EventType.RUN_FINISHED
    assert events[-1].data["run_id"] == stream.run_id
    assert events[-1].data["status"] == "completed"
    assert stream.is_complete is True
    assert stream.status == "completed"


def test_reply_events_with_runtime_reports_prepare_failure_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken_prepare(*args, **kwargs):
        raise RuntimeError("profile setup failed")

    async def run() -> tuple[list[EventType], FakeLLM]:
        runtime, services, llm = _runtime(tmp_path)
        events = []
        async for event in reply_events_with_runtime(
            EngineRequest(message="hello"),
            runtime,
            services,
        ):
            events.append(event)
        return [event.type for event in events], llm

    monkeypatch.setattr(agent_loop_module, "prepare_runtime", broken_prepare)
    event_types, llm = asyncio.run(run())

    assert event_types == [
        EventType.RUN_STARTED,
        EventType.TEXT_DELTA,
        EventType.FAILED,
        EventType.DONE,
        EventType.RUN_FINISHED,
    ]
    assert llm.closed is True

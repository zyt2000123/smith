from __future__ import annotations

import asyncio
from pathlib import Path

from engine.execution.agent_loop import reply_events_with_runtime, reply_with_runtime
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

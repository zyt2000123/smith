from __future__ import annotations

import asyncio
from pathlib import Path

from engine.execution.agent_loop import run_agent_stream
from engine.execution.backtrack import FailureLoopGuard
from engine.execution.events import EventType
from engine.execution.gate import GateResult
from engine.execution.skill_chain import SkillChain, SkillNode
from engine.execution.task_router import TaskType
from engine.llm.client import ChatResponse
from engine.llm.events import ProviderEvent, ProviderEventType
from engine.skill.loader import SkillBody, SkillMeta


class FakeLLM:
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        prefix_cache_key: str | None = None,
    ) -> ChatResponse:
        return ChatResponse(
            text=(
                "Completed the requested work with evidence in "
                "engine/execution/agent_loop.py and enough detail for review."
            )
        )


class StreamingFakeLLM(FakeLLM):
    stream = True

    async def chat_events(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ):
        text = (
            "Completed the requested work with evidence in "
            "engine/execution/agent_loop.py and enough detail for review."
        )
        yield ProviderEvent(ProviderEventType.RESPONSE_CREATED)
        yield ProviderEvent(ProviderEventType.OUTPUT_TEXT_DELTA, {"delta": text})
        yield ProviderEvent(
            ProviderEventType.RESPONSE_COMPLETED,
            {"finish_reason": "stop", "raw_finish_reason": "stop"},
        )


class FakeToolRegistry:
    def get_schemas(self) -> list[dict]:
        return []


class FakeSkillRegistry:
    def get(self, name: str) -> SkillBody:
        return SkillBody(meta=SkillMeta(name=name), content="Do the work.")


class PassingGate:
    async def check(self, output: str, context: dict) -> GateResult:
        return GateResult("pass", "ok")


def test_run_agent_stream_saves_and_clears_checkpoint(tmp_path: Path) -> None:
    async def run() -> bool:
        state_path = tmp_path / "sessions" / ".state" / "sess-1.json"
        saw_checkpoint = False

        async for event in run_agent_stream(
            FakeLLM(),
            "system prompt",
            "build a feature",
            FakeToolRegistry(),
            FakeSkillRegistry(),
            TaskType.FEATURE,
            SkillChain([SkillNode("planning", PassingGate())]),
            FailureLoopGuard(),
            execution_context={
                "agent_id": "emp-1",
                "session_id": "sess-1",
                "_profile_dir": str(tmp_path),
            },
        ):
            if event.type == EventType.SKILL_END:
                saw_checkpoint = state_path.is_file()

        assert not state_path.exists()
        return saw_checkpoint

    assert asyncio.run(run())


def test_run_agent_stream_forwards_provider_events_from_skill_nodes() -> None:
    async def run():
        events = []
        async for event in run_agent_stream(
            StreamingFakeLLM(),
            "system prompt",
            "build a feature",
            FakeToolRegistry(),
            FakeSkillRegistry(),
            TaskType.FEATURE,
            SkillChain([SkillNode("planning", PassingGate())]),
            FailureLoopGuard(),
        ):
            events.append(event)
        return events

    events = asyncio.run(run())

    assert any(event.type == EventType.PROVISIONAL_TEXT_DELTA for event in events)
    assert any(event.type == EventType.PROVISIONAL_COMMIT for event in events)
    assert [event.data["text"] for event in events if event.type == EventType.TEXT_DELTA] == [
        "Completed the requested work with evidence in "
        "engine/execution/agent_loop.py and enough detail for review."
    ]

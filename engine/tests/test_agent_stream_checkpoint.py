from __future__ import annotations

import asyncio
from pathlib import Path

from engine.execution import agent_loop as agent_loop_module
from engine.execution.agent_loop import run_agent_stream
from engine.execution.backtrack import FailureLoopGuard
from engine.execution.events import EventType, ExecutionEvent
from engine.execution.gate import GateResult, LLMGate
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


class BrokenStreamingFakeLLM(FakeLLM):
    stream = True

    async def chat_events(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ):
        yield ProviderEvent(ProviderEventType.RESPONSE_CREATED)
        yield ProviderEvent(ProviderEventType.OUTPUT_TEXT_DELTA, {"delta": "unfinished draft"})
        raise RuntimeError("provider disconnected")


class RetryingStreamingFakeLLM(FakeLLM):
    stream = True

    def __init__(self) -> None:
        self.outputs = [
            "first draft",
            "second draft",
            "Detailed accepted output with evidence from engine/example.py and verification details.",
        ]

    async def chat_events(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ):
        yield ProviderEvent(ProviderEventType.RESPONSE_CREATED)
        yield ProviderEvent(ProviderEventType.OUTPUT_TEXT_DELTA, {"delta": self.outputs.pop(0)})
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


class RecordingLLMGate(LLMGate):
    def __init__(self) -> None:
        self.selected_llm = None

    def set_llm(self, llm) -> None:
        self.selected_llm = llm

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

    provisional = next(event for event in events if event.type == EventType.PROVISIONAL_TEXT_DELTA)
    assert len(provisional.data["provision_id"].rsplit(":", 1)[-1]) == 32
    assert any(event.type == EventType.PROVISIONAL_COMMIT for event in events)
    final = [event for event in events if event.type == EventType.TEXT_DELTA]
    assert final == [
        ExecutionEvent(EventType.TEXT_DELTA, {
            "text": "Completed the requested work with evidence in "
            "engine/execution/agent_loop.py and enough detail for review.",
            "already_streamed": True,
        })
    ]


def test_run_agent_stream_routes_llm_gates_to_gate_client() -> None:
    async def run() -> RecordingLLMGate:
        gate = RecordingLLMGate()
        primary_llm = FakeLLM()
        gate_llm = FakeLLM()
        async for _ in run_agent_stream(
            primary_llm,
            "system prompt",
            "build a feature",
            FakeToolRegistry(),
            FakeSkillRegistry(),
            TaskType.FEATURE,
            SkillChain([SkillNode("planning", gate)]),
            FailureLoopGuard(),
            gate_llm=gate_llm,
        ):
            pass
        assert gate.selected_llm is gate_llm
        return gate

    asyncio.run(run())


def test_forced_skill_marks_final_text_already_streamed() -> None:
    async def run():
        events = []
        async for event in run_agent_stream(
            StreamingFakeLLM(),
            "system prompt",
            "run planning",
            FakeToolRegistry(),
            FakeSkillRegistry(),
            TaskType.DIRECT,
            None,
            FailureLoopGuard(),
            forced_skill="planning",
        ):
            events.append(event)
        return events

    events = asyncio.run(run())
    final = [event for event in events if event.type == EventType.TEXT_DELTA]

    assert final == [
        ExecutionEvent(EventType.TEXT_DELTA, {
            "text": "Completed the requested work with evidence in "
            "engine/execution/agent_loop.py and enough detail for review.",
            "already_streamed": True,
        })
    ]


def test_text_stream_adapter_skips_provisional_text() -> None:
    async def fake_reply_events(*args):
        yield ExecutionEvent(EventType.PROVISIONAL_TEXT_DELTA, {
            "provision_id": "planning:0:0:abc",
            "text": "provisional draft",
        })
        yield ExecutionEvent(EventType.PROVISIONAL_COMMIT, {"provision_id": "planning:0:0:abc"})
        yield ExecutionEvent(EventType.TEXT_DELTA, {"text": "final answer", "already_streamed": True})

    async def run() -> list[str]:
        original = agent_loop_module.reply_events_with_runtime
        agent_loop_module.reply_events_with_runtime = fake_reply_events
        try:
            return [
                chunk
                async for chunk in agent_loop_module.reply_stream_with_runtime(None, None, None)
            ]
        finally:
            agent_loop_module.reply_events_with_runtime = original

    assert asyncio.run(run()) == ["final answer"]


def test_pipeline_retracts_provisional_draft_before_propagating_provider_error() -> None:
    async def run():
        events = []
        try:
            async for event in run_agent_stream(
                BrokenStreamingFakeLLM(),
                "system prompt",
                "build a feature",
                FakeToolRegistry(),
                FakeSkillRegistry(),
                TaskType.FEATURE,
                SkillChain([SkillNode("planning", PassingGate())]),
                FailureLoopGuard(),
            ):
                events.append(event)
        except RuntimeError as exc:
            assert str(exc) == "provider disconnected"
        return events

    events = asyncio.run(run())
    provisional = next(event for event in events if event.type == EventType.PROVISIONAL_TEXT_DELTA)
    retraction = next(event for event in events if event.type == EventType.PROVISIONAL_RETRACT)

    assert retraction.data == {
        "provision_id": provisional.data["provision_id"],
        "reason": "execution_error",
    }


def test_pipeline_retracts_each_rejected_rubric_attempt_before_committing() -> None:
    async def run():
        events = []
        async for event in run_agent_stream(
            RetryingStreamingFakeLLM(),
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
    provision_ids = [
        event.data["provision_id"]
        for event in events
        if event.type == EventType.PROVISIONAL_TEXT_DELTA
    ]
    retracted_ids = [
        event.data["provision_id"]
        for event in events
        if event.type == EventType.PROVISIONAL_RETRACT
    ]
    committed_ids = [
        event.data["provision_id"]
        for event in events
        if event.type == EventType.PROVISIONAL_COMMIT
    ]

    assert len(provision_ids) == 3
    assert retracted_ids == provision_ids[:2]
    assert committed_ids == provision_ids[2:]

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from engine.execution import agent_loop as agent_loop_module
from engine.execution.agent_loop import (
    prepare_runtime,
    reply_events_with_runtime,
    reply_with_runtime,
    run_stream_with_runtime,
)
from engine.execution.events import EventType
from engine.execution.run_state import RunStateStore, RunStatus
from engine.execution.runtime import EngineRequest, RuntimeContext, RuntimeServices
from engine.identity_catalog import IdentityCatalog
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


class ToolCallingMemoryLLM(ToolCallingLLM):
    def __init__(self) -> None:
        super().__init__()
        self.chat_calls: list[list[dict]] = []

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        prefix_cache_key: str | None = None,
    ) -> ChatResponse:
        self.chat_calls.append(messages)
        self.messages = messages
        if self.responses:
            return self.responses.pop(0)
        return ChatResponse(text="stable memory summary")


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
    identities_dir = agents_dir / "identities"
    identities_dir.mkdir()
    (identities_dir / "smith.yaml").write_text(
        """
schema: agentsmith.identity/v1
id: smith
name: Smith
default: true
routes: []
""".strip(),
        encoding="utf-8",
    )

    llm = FakeLLM()
    runtime = RuntimeContext(
        agent_id="smith",
        agent_name="Smith",
        profile_dir=profile_dir,
        agents_dir=agents_dir,
        session_id="sess-1",
        identity_catalog=IdentityCatalog.load(identities_dir),
    )
    services = RuntimeServices(
        llm=llm,  # type: ignore[arg-type]
        tool_registry=ToolRegistry(),
        skill_registry=SkillRegistry(),
    )
    return runtime, services, llm


def test_prepare_runtime_binds_memory_ops_but_keeps_it_hidden(tmp_path: Path) -> None:
    async def run() -> tuple[list[str], list[dict]]:
        runtime, services, _ = _runtime(tmp_path)
        tools_dir = runtime.agents_dir / "tools"
        tools_dir.mkdir(exist_ok=True)
        memory_ops_src = Path(__file__).resolve().parents[2] / "agents" / "tools" / "memory_ops.py"
        (tools_dir / "memory_ops.py").write_text(memory_ops_src.read_text(encoding="utf-8"), encoding="utf-8")
        (runtime.profile_dir / "config.yaml").write_text("tools:\n  enabled: [memory_ops]\n", encoding="utf-8")

        await prepare_runtime(EngineRequest(message="hello"), runtime, services)
        return (
            services.tool_registry.list_tool_names(include_disabled=True),
            services.tool_registry.get_schemas(),
        )

    tool_names, schemas = asyncio.run(run())

    assert "memory_ops" in tool_names
    assert all(schema["function"]["name"] != "memory_ops" for schema in schemas)


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
        assert not (runtime.profile_dir / "identity-state" / "smith" / "memory" / "recent.jsonl").exists()
        return llm

    llm = asyncio.run(run())
    assert llm.closed is True
    assert llm.messages[-1]["content"] == "hello\n\ncwd=/tmp/work"
    assert "agent_id: smith" in llm.messages[0]["content"]
    assert "_profile_dir:" in llm.messages[0]["content"]


def test_run_stream_persists_queued_and_terminal_run_state(tmp_path: Path) -> None:
    async def run() -> tuple[str, RunStatus, int]:
        runtime, services, _ = _runtime(tmp_path)
        stream = run_stream_with_runtime(EngineRequest(message="hello"), runtime, services)
        store = RunStateStore(runtime.profile_dir)
        queued = store.get(stream.run_id)
        assert queued is not None
        assert queued.status is RunStatus.QUEUED

        events = [event async for event in stream.stream_events()]
        finished = store.get(stream.run_id)
        assert finished is not None
        assert finished.status is RunStatus.COMPLETED
        assert finished.last_event_type == EventType.RUN_FINISHED.value
        assert finished.event_seq == len(events)
        return stream.run_id, finished.status, finished.event_seq

    run_id, status, event_seq = asyncio.run(run())
    assert run_id
    assert status is RunStatus.COMPLETED
    assert event_seq > 1


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


def test_runtime_reuses_llm_for_memory_compilation(tmp_path: Path) -> None:
    async def run() -> ToolCallingMemoryLLM:
        runtime, services, _ = _runtime(tmp_path)
        llm = ToolCallingMemoryLLM()
        services.llm = llm  # type: ignore[assignment]
        state_dir = runtime.profile_dir / "memory"
        state_dir.mkdir(parents=True)
        (state_dir / ".compile_counter").write_text("4", encoding="utf-8")

        result = await reply_with_runtime(EngineRequest(message="use a tool"), runtime, services)

        assert result.had_tools is True
        assert (state_dir / "recent.md").is_file()
        assert (state_dir / "durable.md").is_file()
        assert (state_dir / ".compile_counter").read_text(encoding="utf-8") == "0"
        return llm

    llm = asyncio.run(run())

    assert llm.closed is True
    assert len(llm.chat_calls) >= 3
    assert any(
        messages[0]["content"].startswith("You are a memory compiler")
        for messages in llm.chat_calls
    )


def test_prepare_runtime_resolves_a_yaml_route_to_its_pipeline(tmp_path: Path) -> None:
    async def run():
        runtime, services, _ = _runtime(tmp_path)
        identities_dir = runtime.agents_dir / "identities"
        (identities_dir / "smith.yaml").write_text(
            """
schema: agentsmith.identity/v1
id: smith
name: Smith
default: true
routes:
  - id: refactor
    keywords: [重构]
    pipeline: refactor
""".strip(),
            encoding="utf-8",
        )
        pipelines_dir = runtime.agents_dir / "pipelines"
        pipelines_dir.mkdir()
        (pipelines_dir / "refactor.yaml").write_text(
            """
name: refactor
route: refactor
steps:
  - skill: planning
    gate: runtime_contract_planning
""".strip(),
            encoding="utf-8",
        )
        gates_dir = runtime.agents_dir / "gates"
        gates_dir.mkdir()
        (gates_dir / "planning.py").write_text(
            """
from engine.execution.gate import Gate, GateResult

class AlwaysPassGate(Gate):
    async def check(self, output, context):
        return GateResult("pass", "ok")

GATES = {"runtime_contract_planning": AlwaysPassGate}
""".strip(),
            encoding="utf-8",
        )
        runtime = RuntimeContext(
            agent_id=runtime.agent_id,
            agent_name=runtime.agent_name,
            profile_dir=runtime.profile_dir,
            agents_dir=runtime.agents_dir,
            session_id=runtime.session_id,
            identity_catalog=IdentityCatalog.load(identities_dir),
        )
        return await prepare_runtime(EngineRequest(message="请重构这个模块"), runtime, services)

    setup = asyncio.run(run())

    assert setup.route.identity_id == "smith"
    assert setup.route.route_id == "refactor"
    assert setup.route.pipeline_id == "refactor"
    assert setup.chain is not None
    assert [node.skill_name for node in setup.chain.nodes] == ["planning"]


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


def test_runtime_services_close_leaves_borrowed_llm_clients_open(tmp_path: Path) -> None:
    runtime, services, llm = _runtime(tmp_path)
    gate_llm = FakeLLM()
    services.gate_llm = gate_llm  # type: ignore[assignment]
    services.owns_llm_clients = False

    asyncio.run(services.close())

    assert runtime.agent_id == "smith"
    assert llm.closed is False
    assert gate_llm.closed is False


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

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.execution import agent_loop as agent_loop_module
from engine.execution.agent_loop import (
    _bind_working_directory_tools,
    prepare_runtime,
    reply_events_with_runtime,
    reply_with_runtime,
    resume_stream_with_runtime,
    run_stream_with_runtime,
)
from engine.execution.events import EventType, ExecutionEvent, raw_text_delta
from engine.execution.run_state import RunStateStore, RunStatus
from engine.execution.runtime import EngineRequest, RuntimeContext, RuntimeServices
from engine.identity_catalog import IdentityCatalog
from engine.llm.client import ChatResponse, ToolCallData
from engine.safety.tool_guard import ToolGuard
from engine.skill.registry import SkillRegistry
from engine.tool.interface import ToolCall
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
        prompt = messages[-1]["content"]
        if "`memory/recent.md`" in prompt:
            return ChatResponse(text="""# Recent Working Memory

## Active Work
- **Runtime memory** — 状态：active；下一步：verify；更新：2026-07-13。

## Pending

## Recent Verified Outcomes
""")
        if "`memory/durable.md`" in prompt:
            return ChatResponse(text="""# Durable Project Memory

## Confirmed Facts
- **Runtime memory**: Tool-assisted turns enter the memory pipeline.

## Decisions

## Reusable Procedures

## Known Pitfalls
""")
        return ChatResponse(text="stable memory summary")


class PassReviewer(FakeLLM):
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        prefix_cache_key: str | None = None,
    ) -> ChatResponse:
        self.messages = messages
        return ChatResponse(
            text='{"pass": true, "hard_fail": [], "soft_fail": [], "feedback": ""}'
        )


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


def test_prepare_runtime_scopes_tool_paths_to_the_request_working_dir(tmp_path: Path) -> None:
    async def run() -> tuple[ToolCall, ToolCall, ToolCall, ToolGuard]:
        runtime, services, _ = _runtime(tmp_path)
        project_dir = tmp_path / "OpenAI_project"
        project_dir.mkdir()
        services.tool_registry.register(
            "write_file",
            "",
            {"type": "object", "properties": {"path": {"type": "string"}}},
            lambda **_kwargs: "OK",
            path_args=("path",),
            is_write_tool=True,
        )
        services.tool_registry.register(
            "shell",
            "",
            {"type": "object", "properties": {"cwd": {"type": "string"}}},
            lambda **_kwargs: "OK",
            path_args=("cwd",),
        )
        guard = ToolGuard(tmp_path / "missing-rules.json")
        services.tool_guard = guard

        await prepare_runtime(
            EngineRequest(message="Inspect the project", working_dir=str(project_dir)),
            runtime,
            services,
        )
        write = services.tool_registry.normalize_call(
            ToolCall(
                id="write",
                name="write_file",
                arguments={"path": "app/main.py", "content": "x"},
            )
        )
        shell = services.tool_registry.normalize_call(
            ToolCall(id="shell", name="shell", arguments={"command": "test -d . 2>/dev/null"})
        )
        escaped = services.tool_registry.normalize_call(
            ToolCall(id="escaped", name="write_file", arguments={"path": "../outside.txt", "content": "x"})
        )
        return write, shell, escaped, guard

    write, shell, escaped, guard = asyncio.run(run())

    assert write.arguments["path"] == str(
        (tmp_path / "OpenAI_project" / "app" / "main.py").resolve()
    )
    assert shell.arguments["cwd"] == str((tmp_path / "OpenAI_project").resolve())
    assert guard.check(write).allowed
    assert not guard.check(shell).allowed
    assert not guard.check(escaped).allowed


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


def test_prepare_runtime_keeps_recent_and_retrieves_only_matching_durable(
    tmp_path: Path,
) -> None:
    async def run() -> str:
        runtime, services, _ = _runtime(tmp_path)
        memory_dir = runtime.profile_dir / "memory"
        memory_dir.mkdir()
        (memory_dir / "recent.md").write_text(
            "# Recent Working Memory\n\n## Active Work\n- RECENT_ACTIVE_WORK\n",
            encoding="utf-8",
        )
        (memory_dir / "durable.md").write_text(
            "# Durable Project Memory\n\n"
            "## Confirmed Facts\n"
            "- PostgreSQL migration uses Alembic.\n"
            "- Redis caching uses a separate worker.\n",
            encoding="utf-8",
        )

        setup = await prepare_runtime(
            EngineRequest(message="Continue the PostgreSQL migration"),
            runtime,
            services,
        )
        return setup.system_prompt

    prompt = asyncio.run(run())

    assert "RECENT_ACTIVE_WORK" in prompt
    assert "PostgreSQL migration uses Alembic" in prompt
    assert "Redis caching uses a separate worker" not in prompt


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


def test_resume_setup_failure_is_exposed_as_terminal_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, services, llm = _runtime(tmp_path)

    def fail_store(_profile_dir: Path):
        raise OSError("runs directory unavailable")

    monkeypatch.setattr(agent_loop_module, "RunStateStore", fail_store)

    async def collect():
        stream = resume_stream_with_runtime(
            EngineRequest(message="resume"), runtime, services, "missing-run"
        )
        return stream, [event async for event in stream.stream_events()]

    stream, events = asyncio.run(collect())

    assert events[-1].type is EventType.RUN_FINISHED
    assert events[-1].data == {
        "run_id": "missing-run",
        "status": "failed",
        "reason": "resume_setup_failed",
    }
    assert stream.is_complete is True
    assert stream.status == "failed"
    assert llm.closed is True


def test_resume_stream_enables_ledger_replay_for_new_provider_call_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, services, _ = _runtime(tmp_path)
    store = RunStateStore(runtime.profile_dir)
    store.create("run-1", agent_id=runtime.agent_id)
    store.transition("run-1", RunStatus.RUNNING)
    store.transition("run-1", RunStatus.INCOMPLETE)
    captured: dict[str, object] = {}

    class RecordingLedger:
        def __init__(self, profile_dir: Path, run_id: str, *, replay_existing: bool = False):
            captured["profile_dir"] = profile_dir
            captured["run_id"] = run_id
            captured["replay_existing"] = replay_existing

    async def fake_events(*_args, **_kwargs):
        if False:
            yield None

    monkeypatch.setattr(agent_loop_module, "ToolExecutionLedger", RecordingLedger)
    monkeypatch.setattr(agent_loop_module, "_run_events_with_runtime", fake_events)

    resume_stream_with_runtime(EngineRequest(message="resume"), runtime, services, "run-1")

    assert captured == {
        "profile_dir": runtime.profile_dir,
        "run_id": "run-1",
        "replay_existing": True,
    }


def test_working_directory_adapter_binds_file_shell_and_git_arguments(tmp_path: Path) -> None:
    async def run() -> list[tuple[str, dict]]:
        calls: list[tuple[str, dict]] = []

        async def capture(name: str, **kwargs) -> str:
            calls.append((name, kwargs))
            return "OK"

        def handler_for(name: str):
            async def handler(**kwargs) -> str:
                return await capture(name, **kwargs)

            return handler

        registry = ToolRegistry()
        for tool_name in ("write_file", "edit_file", "shell", "git_ops"):
            registry.register(
                tool_name,
                "",
                {},
                handler_for(tool_name),
            )
        services = RuntimeServices(
            llm=FakeLLM(),
            tool_registry=registry,
            skill_registry=SkillRegistry(),
        )
        _bind_working_directory_tools(services, tmp_path)

        await registry.execute(
            ToolCall(id="write", name="write_file", arguments={"path": "notes.txt", "content": "x"})
        )
        await registry.execute(
            ToolCall(id="edit", name="edit_file", arguments={"path": "nested/notes.txt"})
        )
        await registry.execute(
            ToolCall(id="shell", name="shell", arguments={"command": "pwd"})
        )
        await registry.execute(
            ToolCall(
                id="git",
                name="git_ops",
                arguments={"action": "status", "cwd": "repo", "path": "repo/file.txt"},
            )
        )
        return calls

    calls = asyncio.run(run())
    root = str(tmp_path.resolve())

    assert calls == [
        ("write_file", {"path": f"{root}/notes.txt", "content": "x", "_work_dir": root}),
        ("edit_file", {"path": f"{root}/nested/notes.txt", "_work_dir": root}),
        ("shell", {"command": "pwd", "cwd": root}),
        ("git_ops", {"action": "status", "cwd": f"{root}/repo", "path": f"{root}/repo/file.txt"}),
    ]


def test_incomplete_run_persists_learning_with_partial_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, services, _ = _runtime(tmp_path)
    identity = runtime.identity_catalog.get("smith")  # type: ignore[union-attr]
    setup = SimpleNamespace(
        system_prompt="system",
        identity=identity,
        route=SimpleNamespace(identity_id="smith", route_id="direct", pipeline_id=None),
        chain=None,
        state_dir=runtime.profile_dir,
    )
    captured: dict[str, object] = {}

    async def fake_prepare_runtime(*_args, **_kwargs):
        return setup

    async def fake_run_agent_stream(*_args, **_kwargs):
        yield ExecutionEvent(EventType.TOOL_CALL_START, {"name": "search"})
        yield ExecutionEvent(EventType.TEXT_DELTA, {"text": "partial result"})
        yield ExecutionEvent(EventType.INCOMPLETE, {"reason": "model_output_limit"})

    async def fake_persist(*_args, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(agent_loop_module, "prepare_runtime", fake_prepare_runtime)
    monkeypatch.setattr(agent_loop_module, "run_agent_stream", fake_run_agent_stream)
    monkeypatch.setattr(agent_loop_module, "_persist_runtime_learning", fake_persist)

    async def collect():
        stream = run_stream_with_runtime(EngineRequest(message="continue"), runtime, services)
        return [event async for event in stream.stream_events()]

    events = asyncio.run(collect())

    assert captured == {
        "terminal_status": "incomplete",
        "terminal_reason": "model_output_limit",
    }
    assert events[-1].data["status"] == "incomplete"


def test_raw_text_delta_uses_normalized_provider_event_contract() -> None:
    event = ExecutionEvent(
        EventType.RAW_RESPONSE_EVENT,
        {
            "type": "response.output_text.delta",
            "data": {"delta": "hello"},
        },
    )
    provisional = ExecutionEvent(
        EventType.RAW_RESPONSE_EVENT,
        {
            "type": "response.output_text.delta",
            "provision_id": "draft-1",
            "data": {"delta": "draft"},
        },
    )

    assert raw_text_delta(event, include_provisional=False) == "hello"
    assert raw_text_delta(provisional, include_provisional=False) is None
    assert raw_text_delta(provisional) == "draft"


def test_agent_loop_public_exports_exclude_react_implementation_aliases() -> None:
    assert "run_stream_with_runtime" in agent_loop_module.__all__
    assert "_react_event_loop" not in agent_loop_module.__all__
    assert "_react_loop" not in agent_loop_module.__all__
    assert "_react_stream_loop" not in agent_loop_module.__all__


def test_run_stream_bounds_post_run_learning_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow_persist(*_args, **_kwargs):
        await asyncio.sleep(1)
        return True

    monkeypatch.setattr(agent_loop_module, "_persist_runtime_learning", slow_persist)
    monkeypatch.setattr(agent_loop_module, "_RUNTIME_LEARNING_TIMEOUT_SECONDS", 0.01, raising=False)

    async def collect_events():
        runtime, services, _ = _runtime(tmp_path)
        stream = run_stream_with_runtime(EngineRequest(message="hello"), runtime, services)
        return [event async for event in stream.stream_events()]

    events = asyncio.run(asyncio.wait_for(collect_events(), timeout=0.2))

    assert events[-1].type is EventType.RUN_FINISHED


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
        services.gate_llm = PassReviewer()  # type: ignore[assignment]
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
        messages[0]["content"].startswith("You are Smith's memory compiler")
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
    background_llm = FakeLLM()
    services.gate_llm = gate_llm  # type: ignore[assignment]
    services.background_llm = background_llm  # type: ignore[assignment]

    asyncio.run(services.close())

    assert runtime.agent_id == "smith"
    assert llm.closed is True
    assert gate_llm.closed is True
    assert background_llm.closed is True


def test_runtime_services_close_leaves_borrowed_llm_clients_open(tmp_path: Path) -> None:
    runtime, services, llm = _runtime(tmp_path)
    gate_llm = FakeLLM()
    background_llm = FakeLLM()
    services.gate_llm = gate_llm  # type: ignore[assignment]
    services.owns_llm_clients = False
    services.background_llm = background_llm  # type: ignore[assignment]

    asyncio.run(services.close())

    assert runtime.agent_id == "smith"
    assert llm.closed is False
    assert gate_llm.closed is False
    assert background_llm.closed is False


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

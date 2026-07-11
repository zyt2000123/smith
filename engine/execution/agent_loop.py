"""Agent loop — routing, lifecycle, and entry points.

This is the top-level orchestrator. It does NOT execute pipelines or run
ReAct loops directly; it delegates to pipeline.py and react_loop.py.

Responsibilities:
  1. prepare_runtime()  — load tools, skills, memory, assemble prompt, route
  2. run_agent_stream() — route to DIRECT / pipeline / forced-skill
  3. Lifecycle          — persistence, cleanup, terminal state
  4. Entry points       — run_stream_with_runtime, reply_with_runtime, etc.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, AsyncGenerator, Callable, NamedTuple
from pathlib import Path
from uuid import uuid4

if TYPE_CHECKING:
    pass

from engine.llm.client import LLMClient
from engine.prompt.assembler import PromptAssembler
from engine.react_budget import DEFAULT_MAX_REACT_ITERS
from engine.safety.fact_gate import FactGate, FactGateContext, use_fact_gate
from engine.safety.tool_guard import ToolGuard
from engine.skill.executor import execute_skill_events
from engine.skill.registry import SkillRegistry
from engine.tool.registry import ToolRegistry
from .backtrack import FailureLoopGuard
from .events import EventType, ExecutionEvent
from .pipeline import run_pipeline
from .react_loop import (
    FailedAgentRunError,
    IncompleteAgentRunError,
    react_event_loop as _react_event_loop,
    react_loop as _react_loop,
    react_stream_loop as _react_stream_loop,
)
from .run_stream import AgentRunStream
from .runtime import EngineRequest, EngineResult, RuntimeContext, RuntimeServices
from .skill_chain import SkillChain
from .task_router import (
    EVAL_SENSITIVE_GUIDANCE,
    TaskType,
    detect_eval_sensitive,
    route_task,
)

__all__ = ("_react_event_loop", "_react_loop", "_react_stream_loop")

logger = logging.getLogger(__name__)

_HIDDEN_DEFAULT_TOOLS = frozenset({
    "memory_ops",
    "search_knowledge",
    "skill_load",
    "skill_manage",
})


# ---------------------------------------------------------------------------
# Core: routing + dispatch
# ---------------------------------------------------------------------------


async def run_agent_stream(
    llm: LLMClient,
    system_prompt: str,
    user_message: str,
    tool_registry: ToolRegistry,
    skill_registry: SkillRegistry,
    task_type: TaskType,
    skill_chain: SkillChain | None,
    guard: FailureLoopGuard,
    tool_guard: ToolGuard | None = None,
    max_react_iters: int = DEFAULT_MAX_REACT_ITERS,
    history: list[dict] | None = None,
    forced_skill: str | None = None,
    execution_context: dict | None = None,
) -> AsyncGenerator[ExecutionEvent, None]:
    """Route to the right execution path and yield events."""
    if forced_skill:
        async for event in _run_forced_skill_stream(
            llm, system_prompt, tool_registry, skill_registry,
            user_message, forced_skill, tool_guard, max_react_iters,
            history=history, execution_context=execution_context,
        ):
            yield event
        return

    base_messages = [
        {"role": "system", "content": system_prompt},
        *(history or []),
        {"role": "user", "content": user_message},
    ]

    yield ExecutionEvent(EventType.ROUTE_DECIDED, {"type": task_type.value})

    if task_type == TaskType.DIRECT or skill_chain is None:
        async for event in _react_event_loop(llm, base_messages, tool_registry, tool_guard, max_react_iters):
            yield event
        yield ExecutionEvent(EventType.DONE, {})
        return

    context: dict = {"user_message": user_message, "task_type": task_type.value}
    if execution_context:
        context.update({k: v for k, v in execution_context.items() if v is not None})

    async for event in run_pipeline(
        skill_chain, llm, user_message, base_messages,
        tool_registry, skill_registry, tool_guard, guard,
        max_react_iters, context,
    ):
        yield event


# ---------------------------------------------------------------------------
# Forced skill execution
# ---------------------------------------------------------------------------


async def _run_forced_skill_stream(
    llm: LLMClient,
    system_prompt: str,
    tool_registry: ToolRegistry,
    skill_registry: SkillRegistry,
    user_message: str,
    forced_skill: str,
    tool_guard: ToolGuard | None,
    max_react_iters: int,
    history: list[dict] | None = None,
    execution_context: dict | None = None,
) -> AsyncGenerator[ExecutionEvent, None]:
    yield ExecutionEvent(EventType.ROUTE_DECIDED, {"type": "skill", "skill": forced_skill})

    skill = skill_registry.get(forced_skill)
    if skill is None:
        msg = _missing_skill_message(skill_registry, forced_skill)
        yield ExecutionEvent(EventType.BLOCKED, {"skill": forced_skill, "reason": msg})
        yield ExecutionEvent(EventType.TEXT_DELTA, {"text": msg})
        yield ExecutionEvent(EventType.DONE, {})
        return

    yield ExecutionEvent(EventType.SKILL_START, {"skill": forced_skill, "index": 0})
    messages = [
        {"role": "system", "content": system_prompt},
        *(history or []),
        {"role": "user", "content": user_message},
    ]
    context: dict = {"user_message": user_message, "task_type": "skill", "forced_skill": forced_skill}
    if execution_context:
        context.update({k: v for k, v in execution_context.items() if v is not None})
    output_parts: list[str] = []
    terminal_reason: str | None = None
    terminal_type: str | None = None
    async for event in execute_skill_events(
        skill, llm, tool_registry, messages, context,
        max_react_iters, tool_guard=tool_guard,
    ):
        if event.type == EventType.TEXT_DELTA:
            output_parts.append(str(event.data.get("text", "")))
            continue
        elif event.type == EventType.INCOMPLETE:
            terminal_reason = str(event.data.get("reason", "agent_incomplete"))
            terminal_type = "incomplete"
        elif event.type == EventType.FAILED:
            terminal_reason = str(event.data.get("reason", "agent_failed"))
            terminal_type = "failed"
        yield event
    if terminal_type:
        yield ExecutionEvent(EventType.SKILL_END, {"skill": forced_skill, "status": terminal_type})
        if output_parts:
            yield ExecutionEvent(EventType.TEXT_DELTA, {"text": "".join(output_parts)})
        yield ExecutionEvent(EventType.DONE, {})
        return
    output = "".join(output_parts)
    yield ExecutionEvent(EventType.SKILL_END, {"skill": forced_skill, "status": "passed"})
    yield ExecutionEvent(EventType.TEXT_DELTA, {"text": output})
    yield ExecutionEvent(EventType.DONE, {})


# ---------------------------------------------------------------------------
# Runtime preparation
# ---------------------------------------------------------------------------


class _AgentSetup(NamedTuple):
    profile_dir: Path
    system_prompt: str
    task_type: TaskType
    chain: SkillChain | None


def _merge_context(user_message: str, context: str | None) -> str:
    return f"{user_message}\n\n{context}" if context else user_message


def _missing_skill_message(skill_registry: SkillRegistry, forced_skill: str) -> str:
    available = ", ".join(
        sorted(summary["name"] for summary in skill_registry.list_summaries())
    )
    if not available:
        return f"Skill '{forced_skill}' not found. No skills are currently available."
    return f"Skill '{forced_skill}' not found. Available skills: {available}"


def _enabled_tools_from_config(emp_config: dict, tool_registry: ToolRegistry) -> list[str]:
    available = tool_registry.list_tool_names(include_disabled=True)
    tools_cfg = emp_config.get("tools") if isinstance(emp_config, dict) else {}
    enabled = tools_cfg.get("enabled") if isinstance(tools_cfg, dict) else None
    if not isinstance(enabled, list):
        return [name for name in available if name not in _HIDDEN_DEFAULT_TOOLS]
    return [
        name for name in enabled
        if isinstance(name, str) and name and name not in _HIDDEN_DEFAULT_TOOLS
    ]


def _runtime_prompt_context(runtime: RuntimeContext) -> dict[str, str]:
    context = {
        "agent_id": runtime.agent_id,
        "name": runtime.agent_name,
        "_profile_dir": str(runtime.profile_dir),
    }
    if runtime.session_id:
        context["session_id"] = runtime.session_id
    for key, value in runtime.metadata.items():
        context.setdefault(key, value)
    return context


def _runtime_execution_context(runtime: RuntimeContext) -> dict[str, str | None]:
    context: dict[str, str | None] = {
        "agent_id": runtime.agent_id,
        "session_id": runtime.session_id,
        "_profile_dir": str(runtime.profile_dir),
    }
    context.update({key: value for key, value in runtime.metadata.items()})
    return context


async def _load_profile_config(runtime: RuntimeContext) -> dict:
    try:
        from common.yaml_utils import load_yaml
        loaded_config = load_yaml(runtime.profile_dir / "config.yaml")
        if isinstance(loaded_config, dict):
            return loaded_config
    except Exception:
        logger.exception("failed to load agent config (agent=%s)", runtime.agent_id)
    return {}


async def _register_mcp_tools(emp_config: dict, runtime: RuntimeContext, services: RuntimeServices) -> None:
    try:
        mcp_servers = emp_config.get("mcp_servers", [])
        if not mcp_servers:
            return
        from engine.tool.mcp_client import MCPClient, register_mcp_tools
        for srv in mcp_servers:
            cmd = srv.get("command", [])
            if not cmd:
                continue
            client = MCPClient(cmd, env=srv.get("env"))
            await client.connect()
            services.mcp_clients.append(client)
            await register_mcp_tools(services.tool_registry, client)
    except Exception:
        logger.exception("failed to register MCP tools (agent=%s)", runtime.agent_id)


async def prepare_runtime(
    request: EngineRequest,
    runtime: RuntimeContext,
    services: RuntimeServices,
) -> _AgentSetup:
    """Prepare prompt, tools, skills, and task routing from an explicit runtime."""
    services.tool_registry.load_providers(runtime.agents_dir / "tools")
    emp_config = await _load_profile_config(runtime)
    await _register_mcp_tools(emp_config, runtime, services)

    unknown_tools = services.tool_registry.set_enabled(
        _enabled_tools_from_config(emp_config, services.tool_registry)
    )
    if unknown_tools:
        logger.warning(
            "agent %s configured unknown tools ignored: %s",
            runtime.agent_id, ", ".join(sorted(set(unknown_tools))),
        )

    services.skill_registry.load_builtin(runtime.agents_dir / "skills")
    profile_skills = runtime.profile_dir / "skills"
    if profile_skills.is_dir():
        services.skill_registry.load_agent_skills(profile_skills)

    from engine.memory.store import search_relevant_memories
    retrieved = await search_relevant_memories(runtime.profile_dir, request.message)
    assembler = PromptAssembler()
    system_prompt = assembler.assemble(
        runtime.profile_dir, services.tool_registry, services.skill_registry,
        _runtime_prompt_context(runtime), retrieved_memory=retrieved,
    )

    task_type = route_task(request.message)
    if detect_eval_sensitive(request.message):
        system_prompt += "\n\n" + EVAL_SENSITIVE_GUIDANCE

    available_skills = {
        summary["name"] for summary in services.skill_registry.list_summaries()
    }
    chain = _resolve_pipeline(task_type, runtime, available_skills)

    return _AgentSetup(runtime.profile_dir, system_prompt, task_type, chain)


def _resolve_pipeline(
    task_type: TaskType,
    runtime: RuntimeContext,
    available_skills: set[str],
) -> SkillChain | None:
    """Load pipeline: user profile → agents/pipelines/ → built-in fallback."""
    route = task_type.value
    if route == "direct":
        return None

    # 1. User-defined pipeline in profile
    profile_pipelines = runtime.profile_dir / "pipelines"
    if profile_pipelines.is_dir():
        user_chains = SkillChain.load_pipelines(profile_pipelines)
        if route in user_chains:
            return user_chains[route].for_available_skills(available_skills)

    # 2. Built-in pipelines from agents/pipelines/
    builtin_pipelines = runtime.agents_dir / "pipelines"
    if builtin_pipelines.is_dir():
        builtin_chains = SkillChain.load_pipelines(builtin_pipelines)
        if route in builtin_chains:
            return builtin_chains[route].for_available_skills(available_skills)

    # 3. Hardcoded fallback
    _BUILTIN_CHAINS: dict[str, Callable[[], SkillChain]] = {
        "feature": SkillChain.feature_chain,
        "bugfix": SkillChain.bugfix_chain,
    }
    factory = _BUILTIN_CHAINS.get(route)
    if factory:
        return factory().for_available_skills(available_skills)

    return None


# ---------------------------------------------------------------------------
# Lifecycle: persistence + cleanup + terminal state
# ---------------------------------------------------------------------------


async def _persist_runtime_learning(
    runtime: RuntimeContext, user_message: str, reply_text: str, had_tools: bool,
) -> None:
    try:
        from engine.memory.store import save_conversation_memory
        await save_conversation_memory(runtime.profile_dir, user_message, reply_text, had_tools)
    except Exception:
        logger.warning("failed to persist conversation memory", exc_info=True)
    try:
        from engine.memory.user_learner import UserPreferenceLearner
        learner = UserPreferenceLearner(runtime.profile_dir)
        await learner.observe(user_message, reply_text)
    except Exception:
        logger.warning("failed to learn user preferences", exc_info=True)


def _has_memory_worthy_activity(event: ExecutionEvent) -> bool:
    return event.type in (EventType.TOOL_CALL_START, EventType.SKILL_START)


def _fact_gate_for_request(request: EngineRequest, runtime: RuntimeContext) -> FactGate:
    return FactGate(FactGateContext(
        session_id=runtime.session_id or "",
        turn_id=uuid4().hex,
    ))


def run_stream_with_runtime(
    request: EngineRequest,
    runtime: RuntimeContext,
    services: RuntimeServices,
) -> AgentRunStream:
    """Create a typed, single-consumer stream for one Agent run."""
    run_id = uuid4().hex
    return AgentRunStream(
        run_id,
        _run_events_with_runtime(request, runtime, services, run_id),
    )


async def _run_events_with_runtime(
    request: EngineRequest,
    runtime: RuntimeContext,
    services: RuntimeServices,
    run_id: str,
) -> AsyncGenerator[ExecutionEvent, None]:
    """Produce one complete run, including persistence and cleanup."""
    full_text: list[str] = []
    had_tools = False
    terminal_status = "completed"
    terminal_reason: str | None = None
    drained = False

    yield ExecutionEvent(EventType.RUN_STARTED, {"run_id": run_id})
    try:
        s = await prepare_runtime(request, runtime, services)
        guard = FailureLoopGuard()
        with use_fact_gate(_fact_gate_for_request(request, runtime)):
            async for event in run_agent_stream(
                services.llm, s.system_prompt,
                _merge_context(request.message, request.context),
                services.tool_registry, services.skill_registry,
                s.task_type, s.chain, guard,
                tool_guard=services.tool_guard,
                history=request.history,
                forced_skill=request.forced_skill,
                execution_context=_runtime_execution_context(runtime),
            ):
                if event.type == EventType.TEXT_DELTA:
                    full_text.append(str(event.data.get("text", "")))
                elif event.type == EventType.INCOMPLETE:
                    terminal_status = "incomplete"
                    terminal_reason = str(event.data.get("reason", "agent_incomplete"))
                elif event.type == EventType.FAILED:
                    terminal_status = "failed"
                    terminal_reason = str(event.data.get("reason", "agent_failed"))
                elif event.type == EventType.BLOCKED and terminal_status == "completed":
                    terminal_status = "incomplete"
                    terminal_reason = "blocked"
                elif _has_memory_worthy_activity(event):
                    had_tools = True
                yield event
        drained = True
    except Exception as exc:
        logger.exception("agent execution failed (agent=%s)", runtime.agent_id)
        terminal_status = "failed"
        terminal_reason = "execution_error"
        yield ExecutionEvent(EventType.TEXT_DELTA, {
            "text": f"⚠️ 执行失败：{type(exc).__name__}（详情见服务端日志）",
        })
        yield ExecutionEvent(EventType.FAILED, {"reason": terminal_reason})
        yield ExecutionEvent(EventType.DONE, {})
        drained = True
    finally:
        if drained and terminal_status == "completed":
            try:
                await _persist_runtime_learning(
                    runtime, request.message, "".join(full_text), had_tools,
                )
            except Exception:
                logger.warning("failed to finalize conversation memory", exc_info=True)
        try:
            await services.close()
        except Exception:
            logger.warning("failed to close engine runtime services", exc_info=True)

    if drained:
        terminal_data: dict[str, str] = {"run_id": run_id, "status": terminal_status}
        if terminal_reason:
            terminal_data["reason"] = terminal_reason
        yield ExecutionEvent(EventType.RUN_FINISHED, terminal_data)


# ---------------------------------------------------------------------------
# Entry points (non-streaming + compatibility)
# ---------------------------------------------------------------------------


async def reply_with_runtime(
    request: EngineRequest,
    runtime: RuntimeContext,
    services: RuntimeServices,
) -> EngineResult:
    """Run one engine request using the same complete stream lifecycle as SSE."""
    full_text: list[str] = []
    had_tools = False
    incomplete_reason: str | None = None
    failed_reason: str | None = None

    stream = run_stream_with_runtime(request, runtime, services)
    async for event in stream.stream_events():
        if event.type == EventType.TEXT_DELTA:
            full_text.append(str(event.data.get("text", "")))
        elif event.type == EventType.INCOMPLETE:
            incomplete_reason = str(event.data.get("reason", "agent_incomplete"))
        elif event.type == EventType.FAILED:
            failed_reason = str(event.data.get("reason", "agent_failed"))
        elif _has_memory_worthy_activity(event):
            had_tools = True

    if not stream.is_complete:
        raise RuntimeError("Agent run ended before a terminal state was emitted.")
    if stream.status == "failed" or failed_reason:
        raise RuntimeError(failed_reason or stream.reason or "agent_failed")
    if stream.status == "incomplete" or incomplete_reason:
        raise IncompleteAgentRunError(incomplete_reason or stream.reason or "agent_incomplete")

    return EngineResult(text="".join(full_text), had_tools=had_tools)


async def reply_events_with_runtime(
    request: EngineRequest,
    runtime: RuntimeContext,
    services: RuntimeServices,
) -> AsyncGenerator[ExecutionEvent, None]:
    """Compatibility adapter over run_stream_with_runtime."""
    stream = run_stream_with_runtime(request, runtime, services)
    async for event in stream.stream_events():
        yield event


# ---------------------------------------------------------------------------
# Legacy entry points — delegate to legacy.py
# ---------------------------------------------------------------------------


async def reply(
    agent_id: str, name: str, user_message: str,
    history: list[dict] | None = None,
    context: str | None = None,
    forced_skill: str | None = None,
) -> str:
    from .legacy import reply as legacy_reply
    return await legacy_reply(
        agent_id, name, user_message,
        history=history, context=context, forced_skill=forced_skill,
    )


async def reply_events(
    agent_id: str, name: str, user_message: str,
    history: list[dict] | None = None,
    context: str | None = None,
    forced_skill: str | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[ExecutionEvent, None]:
    from .legacy import reply_events as legacy_reply_events
    async for event in legacy_reply_events(
        agent_id, name, user_message,
        history=history, context=context,
        forced_skill=forced_skill, session_id=session_id,
    ):
        yield event


async def reply_stream_with_runtime(
    request: EngineRequest,
    runtime: RuntimeContext,
    services: RuntimeServices,
) -> AsyncGenerator[str, None]:
    """Text-only stream adapter."""
    async for event in reply_events_with_runtime(request, runtime, services):
        if event.type == EventType.RAW_RESPONSE_EVENT:
            raw_type = event.data.get("type")
            raw_data = event.data.get("data")
            if raw_type == "response.output_text.delta" and isinstance(raw_data, dict):
                text = raw_data.get("delta")
                if isinstance(text, str) and text:
                    yield text
        elif event.type == EventType.PROVISIONAL_TEXT_DELTA:
            text = event.data.get("text")
            if isinstance(text, str) and text:
                yield text
        elif event.type == EventType.TEXT_DELTA:
            if not event.data.get("already_streamed"):
                yield event.data.get("text", "")
        elif event.type == EventType.SKILL_START:
            yield f"\n[⚙ {event.data.get('skill', '')}]\n"
        elif event.type == EventType.GATE_RESULT:
            yield f"[门禁: {event.data.get('verdict', '')}] "
        elif event.type == EventType.BACKTRACK:
            yield f"\n[↩ 回退: {event.data.get('from', '')} → {event.data.get('to', '')}]\n"
        elif event.type == EventType.BLOCKED:
            yield f"\n[⛔ 阻断: {event.data.get('reason', '')}]\n"


async def reply_stream(
    agent_id: str, name: str, user_message: str,
    history: list[dict] | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    from .legacy import reply_stream as legacy_reply_stream
    async for chunk in legacy_reply_stream(
        agent_id, name, user_message,
        history=history, session_id=session_id,
    ):
        yield chunk

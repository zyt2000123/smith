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
from typing import AsyncGenerator, NamedTuple
from pathlib import Path
from uuid import uuid4

from engine.identity_catalog import IdentityCatalog, IdentitySpec, RouteDecision
from engine.llm.port import LLMPort
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
from .pipeline_context import (
    CTX_AGENT_ID,
    CTX_FORCED_SKILL,
    CTX_IDENTITY_ID,
    CTX_ROUTE_ID,
    CTX_SESSION_ID,
    CTX_STATE_DIR,
    CTX_TASK_TYPE,
    CTX_USER_MESSAGE,
)
from .react_loop import (
    IncompleteAgentRunError,
    react_event_loop as _react_event_loop,
    react_loop as _react_loop,
    react_stream_loop as _react_stream_loop,
)
from .run_stream import AgentRunStream
from .runtime import EngineRequest, EngineResult, RuntimeContext, RuntimeServices
from .skill_chain import SkillChain, load_gate_content
from engine.safety.eval_guard import EVAL_SENSITIVE_GUIDANCE, detect_eval_sensitive
from .task_router import route_task

__all__ = ("_react_event_loop", "_react_loop", "_react_stream_loop")

logger = logging.getLogger(__name__)

# Design intent: some tools (memory_ops, search_knowledge, skill_load,
# skill_manage) are "infrastructure" tools that should be available to the
# agent but hidden from the user-facing enabled-tools whitelist by default.
# Ideally each tool would declare ``"hidden": True`` in its TOOL_META so
# this list is data-driven rather than hardcoded here.
#
# TODO: Once engine/tool/interface.py supports a ``hidden`` field on
# ToolDefinition (and load_providers propagates TOOL_META["hidden"] into it),
# replace _is_hidden_tool() with a registry query. Until then the names are
# kept here as a transitional measure.
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
    llm: LLMPort,
    system_prompt: str,
    user_message: str,
    tool_registry: ToolRegistry,
    skill_registry: SkillRegistry,
    route: RouteDecision,
    skill_chain: SkillChain | None,
    guard: FailureLoopGuard,
    tool_guard: ToolGuard | None = None,
    max_react_iters: int = DEFAULT_MAX_REACT_ITERS,
    history: list[dict] | None = None,
    forced_skill: str | None = None,
    execution_context: dict | None = None,
    gate_llm: LLMPort | None = None,
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

    yield ExecutionEvent(EventType.ROUTE_DECIDED, route.to_event_data())

    if route.pipeline_id is None or skill_chain is None:
        async for event in _react_event_loop(llm, base_messages, tool_registry, tool_guard, max_react_iters):
            yield event
        yield ExecutionEvent(EventType.DONE, {})
        return

    context: dict = {
        CTX_USER_MESSAGE: user_message,
        CTX_IDENTITY_ID: route.identity_id,
        CTX_ROUTE_ID: route.route_id,
    }
    if execution_context:
        context.update({k: v for k, v in execution_context.items() if v is not None})

    async for event in run_pipeline(
        skill_chain, llm, user_message, base_messages,
        tool_registry, skill_registry, tool_guard, guard,
        max_react_iters, context, gate_llm=gate_llm,
    ):
        yield event


# ---------------------------------------------------------------------------
# Forced skill execution
# ---------------------------------------------------------------------------


async def _run_forced_skill_stream(
    llm: LLMPort,
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
    context: dict = {CTX_USER_MESSAGE: user_message, CTX_TASK_TYPE: "skill", CTX_FORCED_SKILL: forced_skill}
    if execution_context:
        context.update({k: v for k, v in execution_context.items() if v is not None})
    output_parts: list[str] = []
    output_was_streamed = False
    terminal_type: str | None = None
    async for event in execute_skill_events(
        skill, llm, tool_registry, messages, context,
        max_react_iters, tool_guard=tool_guard,
        react_event_loop_fn=_react_event_loop,
    ):
        if event.type == EventType.TEXT_DELTA:
            output_parts.append(str(event.data.get("text", "")))
            output_was_streamed = output_was_streamed or bool(event.data.get("already_streamed"))
            continue
        elif event.type == EventType.INCOMPLETE:
            terminal_type = "incomplete"
        elif event.type == EventType.FAILED:
            terminal_type = "failed"
        yield event
    if terminal_type:
        yield ExecutionEvent(EventType.SKILL_END, {"skill": forced_skill, "status": terminal_type})
        if output_parts:
            data: dict[str, object] = {"text": "".join(output_parts)}
            if output_was_streamed:
                data["already_streamed"] = True
            yield ExecutionEvent(EventType.TEXT_DELTA, data)
        yield ExecutionEvent(EventType.DONE, {})
        return
    output = "".join(output_parts)
    yield ExecutionEvent(EventType.SKILL_END, {"skill": forced_skill, "status": "passed"})
    data: dict[str, object] = {"text": output}
    if output_was_streamed:
        data["already_streamed"] = True
    yield ExecutionEvent(EventType.TEXT_DELTA, data)
    yield ExecutionEvent(EventType.DONE, {})


# ---------------------------------------------------------------------------
# Runtime preparation
# ---------------------------------------------------------------------------


class _AgentSetup(NamedTuple):
    system_prompt: str
    identity: IdentitySpec
    route: RouteDecision
    chain: SkillChain | None
    state_dir: Path


def _merge_context(user_message: str, context: str | None) -> str:
    return f"{user_message}\n\n{context}" if context else user_message


def _missing_skill_message(skill_registry: SkillRegistry, forced_skill: str) -> str:
    available = ", ".join(
        sorted(summary["name"] for summary in skill_registry.list_summaries())
    )
    if not available:
        return f"Skill '{forced_skill}' not found. No skills are currently available."
    return f"Skill '{forced_skill}' not found. Available skills: {available}"


def _enabled_tools_from_config(
    profile_config: dict,
    tool_registry: ToolRegistry,
    identity: IdentitySpec,
) -> list[str]:
    available = tool_registry.list_tool_names(include_disabled=True)
    tools_cfg = profile_config.get("tools") if isinstance(profile_config, dict) else {}
    enabled = tools_cfg.get("enabled") if isinstance(tools_cfg, dict) else None
    if enabled is None:
        # No whitelist configured → default to all non-hidden tools.
        configured = [name for name in available if name not in _HIDDEN_DEFAULT_TOOLS]
    elif isinstance(enabled, list):
        configured = [
            name for name in enabled
            if isinstance(name, str) and name and name not in _HIDDEN_DEFAULT_TOOLS
        ]
    else:
        # A malformed whitelist (e.g. `enabled: "shell"`) must fail closed, not
        # silently open every tool — a config typo must never grant shell/file access.
        raise ValueError(
            f"tools.enabled must be a list of tool names, got {type(enabled).__name__}"
        )
    if identity.enabled_tools is None:
        return configured
    allowed = set(identity.enabled_tools)
    return [name for name in configured if name in allowed]


def _runtime_prompt_context(runtime: RuntimeContext, identity: IdentitySpec) -> dict[str, str]:
    context = {
        "agent_id": runtime.agent_id,
        "name": runtime.agent_name,
        "identity_id": identity.id,
        "identity_name": identity.name,
        "_profile_dir": str(runtime.profile_dir),
    }
    if runtime.session_id:
        context["session_id"] = runtime.session_id
    for key, value in runtime.metadata.items():
        context.setdefault(key, value)
    return context


def _runtime_execution_context(
    runtime: RuntimeContext,
    identity: IdentitySpec,
    state_dir: Path,
) -> dict[str, str | None]:
    context: dict[str, str | None] = {
        CTX_AGENT_ID: runtime.agent_id,
        CTX_SESSION_ID: runtime.session_id,
        CTX_IDENTITY_ID: identity.id,
        CTX_STATE_DIR: str(state_dir),
    }
    context.update({key: value for key, value in runtime.metadata.items()})
    return context


def _identity_state_dir(runtime: RuntimeContext, identity: IdentitySpec) -> Path:
    """Return the directory for mutable agent state (memory, checkpoints).

    Single-agent design: state lives directly under profile_dir so that
    the assembler (which reads profile_dir/memory/) and the compilation
    pipeline (which writes here) share the same directory.
    """
    return runtime.profile_dir


async def _load_profile_config(runtime: RuntimeContext) -> dict:
    from common.yaml_utils import load_yaml
    # 文件缺失时 load_yaml 返回 {}（正常默认）；配置损坏必须显式失败——
    # 静默回退空配置会把 tools.enabled 白名单反向放开成全量工具（fail-open）。
    return load_yaml(runtime.profile_dir / "config.yaml")


async def _register_mcp_tools(
    profile_config: dict,
    runtime: RuntimeContext,
    services: RuntimeServices,
) -> None:
    from engine.mcp.config import register_mcp_tools as _mcp_register
    await _mcp_register(profile_config, runtime, services)


async def prepare_runtime(
    request: EngineRequest,
    runtime: RuntimeContext,
    services: RuntimeServices,
) -> _AgentSetup:
    """Prepare prompt, tools, skills, and task routing from an explicit runtime."""
    catalog = runtime.identity_catalog or IdentityCatalog.load(runtime.agents_dir / "identities")
    route = route_task(request.message, catalog, identity_id=request.identity_id)
    identity = route.identity
    state_dir = _identity_state_dir(runtime, identity)

    services.tool_registry.load_providers(runtime.agents_dir / "tools")
    _bind_memory_ops_tool(services, state_dir)
    profile_config = await _load_profile_config(runtime)
    await _register_mcp_tools(profile_config, runtime, services)

    unknown_tools = services.tool_registry.set_enabled(
        _enabled_tools_from_config(profile_config, services.tool_registry, identity)
    )
    if unknown_tools:
        logger.warning(
            "agent %s configured unknown tools ignored: %s",
            runtime.agent_id, ", ".join(sorted(set(unknown_tools))),
        )

    # 工具全部注册后把定义绑给守卫，metadata-first 安全检查才能生效。
    if services.tool_guard is not None:
        services.tool_guard.bind_definitions(services.tool_registry.definitions())

    services.skill_registry.load_builtin(runtime.agents_dir / "skills")
    profile_skills = runtime.profile_dir / "skills"
    if profile_skills.is_dir():
        services.skill_registry.load_agent_skills(profile_skills)
    if identity.enabled_skills is not None:
        services.skill_registry.restrict_to(identity.enabled_skills)

    from engine.memory.store import search_relevant_memories
    retrieved = await search_relevant_memories(state_dir, request.message)
    assembler = PromptAssembler()
    wd = Path(request.working_dir) if request.working_dir else Path.cwd()
    system_prompt = assembler.assemble(
        runtime.profile_dir, services.tool_registry, services.skill_registry,
        _runtime_prompt_context(runtime, identity), retrieved_memory=retrieved,
        working_dir=wd,
    )
    if identity.prompt:
        system_prompt += "\n\n---\n\n" + identity.prompt

    if detect_eval_sensitive(request.message):
        system_prompt += "\n\n" + EVAL_SENSITIVE_GUIDANCE

    chain = _resolve_pipeline(route, runtime)

    return _AgentSetup(system_prompt, identity, route, chain, state_dir)


def _bind_memory_ops_tool(services: RuntimeServices, state_dir: Path) -> None:
    memory_dir = state_dir / "memory"

    async def episode_runner(memory_dir: Path, topic: str, related: list[dict]):
        from engine.memory.compile import compact_episode
        return await compact_episode(
            memory_dir,
            services.llm,
            topic,
            related,
            reviewer=services.gate_llm,
        )

    def wrapper(func):
        async def execute_with_memory_context(**kwargs):
            kwargs["memory_dir"] = memory_dir
            kwargs["episode_runner"] = episode_runner
            return await func(**kwargs)
        return execute_with_memory_context

    services.tool_registry.wrap_tool("memory_ops", wrapper)


def _resolve_pipeline(
    route: RouteDecision,
    runtime: RuntimeContext,
) -> SkillChain | None:
    """Resolve a YAML pipeline selected by a declarative route decision."""
    if route.pipeline_id is None:
        return None

    # 门禁/条件实现是内容层资产：解析 pipeline YAML 前必须先注册，
    # 否则 from_yaml 的 gate key 查找会对合法内容报 unknown gate。
    load_gate_content(runtime.agents_dir)

    # 1. User-defined pipeline in profile
    profile_pipelines = runtime.profile_dir / "pipelines"
    if profile_pipelines.is_dir():
        user_chains = SkillChain.load_pipelines(profile_pipelines)
        if route.pipeline_id in user_chains:
            return user_chains[route.pipeline_id]

    # 2. Built-in pipelines from agents/pipelines/
    builtin_pipelines = runtime.agents_dir / "pipelines"
    if builtin_pipelines.is_dir():
        builtin_chains = SkillChain.load_pipelines(builtin_pipelines)
        if route.pipeline_id in builtin_chains:
            return builtin_chains[route.pipeline_id]

    raise RuntimeError(
        f"Route {route.identity_id}:{route.route_id} references missing pipeline {route.pipeline_id!r}"
    )


# ---------------------------------------------------------------------------
# Lifecycle: persistence + cleanup + terminal state
# ---------------------------------------------------------------------------


def _ensure_memory_lifecycle_hooks(services: RuntimeServices) -> None:
    if getattr(services, "_memory_lifecycle_hooks_registered", False):
        return
    from engine.execution.memory_maintenance import (
        MemoryLifecycleHooks,
        MemoryMaintenanceService,
    )
    from engine.hook import HookManager

    if services.hooks is None:
        services.hooks = HookManager()
    services.hooks.register(MemoryLifecycleHooks(
        MemoryMaintenanceService(services.llm, reviewer=services.gate_llm)
    ))
    setattr(services, "_memory_lifecycle_hooks_registered", True)


async def run_memory_idle_tick(memory_dir: Path, services: RuntimeServices) -> bool:
    """Dispatch idle memory maintenance through lifecycle hooks."""
    return await _dispatch_memory_maintenance_tick(
        "memory_idle_tick",
        memory_dir,
        services,
    )


async def run_memory_daily_tick(memory_dir: Path, services: RuntimeServices) -> bool:
    """Dispatch daily memory maintenance through lifecycle hooks."""
    return await _dispatch_memory_maintenance_tick(
        "memory_daily_tick",
        memory_dir,
        services,
    )


async def _dispatch_memory_maintenance_tick(
    hook_name: str,
    memory_dir: Path,
    services: RuntimeServices,
) -> bool:
    _ensure_memory_lifecycle_hooks(services)
    try:
        from engine.hook import HookType

        results = await services.hooks.apply(
            hook_name,
            HookType.PARALLEL,
            args=(memory_dir,),
        )
        return all(result is not False for result in results)
    except Exception:
        logger.warning("failed to dispatch %s", hook_name, exc_info=True)
        return False


async def _persist_runtime_learning(
    state_dir: Path,
    user_message: str,
    reply_text: str,
    had_tools: bool,
    services: RuntimeServices,
) -> bool:
    """Persist memory and preferences. Returns False if any write failed."""
    ok = True
    _ensure_memory_lifecycle_hooks(services)
    try:
        from engine.hook import HookType

        results = await services.hooks.apply(
            "memory_after_turn_completed",
            HookType.PARALLEL,
            args=(state_dir, user_message, reply_text, had_tools),
        )
        ok = all(result is not False for result in results)
    except Exception:
        ok = False
        logger.warning("failed to persist conversation memory", exc_info=True)
    try:
        from engine.memory.user_learner import UserPreferenceLearner
        learner = UserPreferenceLearner(state_dir)
        await learner.observe(user_message, reply_text)
    except Exception:
        ok = False
        logger.warning("failed to learn user preferences", exc_info=True)
    return ok


def _has_memory_worthy_activity(event: ExecutionEvent) -> bool:
    return event.type in (EventType.TOOL_CALL_START, EventType.SKILL_START)


def _fact_gate_for_request(
    request: EngineRequest,
    runtime: RuntimeContext,
    services: RuntimeServices | None = None,
) -> FactGate:
    definitions = services.tool_registry.definitions() if services is not None else None
    return FactGate(FactGateContext(
        session_id=runtime.session_id or "",
        turn_id=uuid4().hex,
    ), tool_registry=definitions)


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
    state_dir: Path | None = None
    memory_persist_failed = False

    yield ExecutionEvent(EventType.RUN_STARTED, {"run_id": run_id})
    try:
        s = await prepare_runtime(request, runtime, services)
        state_dir = s.state_dir
        guard = FailureLoopGuard()
        with use_fact_gate(_fact_gate_for_request(request, runtime, services)):
            async for event in run_agent_stream(
                services.llm, s.system_prompt,
                _merge_context(request.message, request.context),
                services.tool_registry, services.skill_registry,
                s.route, s.chain, guard,
                tool_guard=services.tool_guard,
                history=request.history,
                forced_skill=request.forced_skill,
                execution_context=_runtime_execution_context(runtime, s.identity, s.state_dir),
                gate_llm=services.gate_llm,
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
        if drained and terminal_status == "completed" and state_dir is not None:
            try:
                memory_persist_failed = not await _persist_runtime_learning(
                    state_dir, request.message, "".join(full_text), had_tools, services,
                )
            except Exception:
                memory_persist_failed = True
                logger.warning("failed to finalize conversation memory", exc_info=True)
        try:
            await services.close()
        except Exception:
            logger.warning("failed to close engine runtime services", exc_info=True)

    if drained:
        terminal_data: dict[str, object] = {"run_id": run_id, "status": terminal_status}
        if terminal_reason:
            terminal_data["reason"] = terminal_reason
        if memory_persist_failed:
            # 记忆写入失败对用户默认不可见；在终态事件上打标，
            # 让前端有机会提示"本轮未写入长期记忆"。
            terminal_data["memory_persist_failed"] = True
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


async def reply_stream_with_runtime(
    request: EngineRequest,
    runtime: RuntimeContext,
    services: RuntimeServices,
) -> AsyncGenerator[str, None]:
    """Text-only stream adapter."""
    saw_raw_text = False
    async for event in reply_events_with_runtime(request, runtime, services):
        if event.type == EventType.RAW_RESPONSE_EVENT:
            raw_type = event.data.get("type")
            raw_data = event.data.get("data")
            if (
                raw_type == "response.output_text.delta"
                and not event.data.get("provision_id")
                and isinstance(raw_data, dict)
            ):
                text = raw_data.get("delta")
                if isinstance(text, str) and text:
                    saw_raw_text = True
                    yield text
        elif event.type == EventType.TEXT_DELTA:
            if not event.data.get("already_streamed") or not saw_raw_text:
                yield event.data.get("text", "")
        elif event.type == EventType.SKILL_START:
            yield f"\n[⚙ {event.data.get('skill', '')}]\n"
        elif event.type == EventType.GATE_RESULT:
            yield f"[门禁: {event.data.get('verdict', '')}] "
        elif event.type == EventType.BACKTRACK:
            yield f"\n[↩ 回退: {event.data.get('from', '')} → {event.data.get('to', '')}]\n"
        elif event.type == EventType.BLOCKED:
            yield f"\n[⛔ 阻断: {event.data.get('reason', '')}]\n"

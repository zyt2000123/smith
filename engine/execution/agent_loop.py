from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator, NamedTuple
from uuid import uuid4

if TYPE_CHECKING:
    pass

from engine.llm.client import LLMClient
from engine.prompt.assembler import PromptAssembler
from engine.react_budget import DEFAULT_MAX_REACT_ITERS
from engine.safety.fact_gate import FactGate, FactGateContext, use_fact_gate
from engine.safety.tool_guard import ToolGuard
from engine.skill.executor import execute_skill
from engine.skill.registry import SkillRegistry
from engine.tool.registry import ToolRegistry
from .backtrack import FailureLoopGuard, FailureSignature
from .events import EventType, ExecutionEvent
from .gate import LLMGate, SkillRubricGate
from .react_loop import (
    react_event_loop as _react_event_loop,
    react_loop as _react_loop,
    react_stream_loop as _react_stream_loop,
)
from .runtime import EngineRequest, EngineResult, RuntimeContext, RuntimeServices
from .skill_chain import SkillChain
from .task_router import (
    EVAL_SENSITIVE_GUIDANCE,
    TaskType,
    detect_eval_sensitive,
    route_task,
)

__all__ = ("_react_event_loop", "_react_loop", "_react_stream_loop")

# Shared rubric gate instance — stateless, safe to reuse
_rubric_gate = SkillRubricGate()
_RUBRIC_MAX_RETRIES = 3

logger = logging.getLogger(__name__)
_HIDDEN_DEFAULT_TOOLS = frozenset({
    "memory_ops",
    "search_knowledge",
    "skill_load",
    "skill_manage",
})


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
    """Run the agent as an event stream, yielding ExecutionEvents throughout execution."""
    if forced_skill:
        async for event in _run_forced_skill_stream(
            llm,
            tool_registry,
            skill_registry,
            user_message,
            forced_skill,
            tool_guard,
            max_react_iters,
            history=history,
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
    node_idx = 0
    max_backtracks = 5
    backtrack_count = 0

    while node_idx < len(skill_chain.nodes):
        node = skill_chain.nodes[node_idx]

        if node.condition is not None and not node.condition(context):
            node_idx += 1
            continue

        yield ExecutionEvent(EventType.SKILL_START, {"skill": node.skill_name, "index": node_idx})

        rubric_attempt = 0
        output = ""
        rubric_passed = False

        while rubric_attempt < _RUBRIC_MAX_RETRIES:
            skill = skill_registry.get(node.skill_name)
            if skill is None:
                messages = base_messages + [{"role": "user", "content": f"[Skill: {node.skill_name}] {user_message}"}]
                if rubric_attempt == 1 and context.get("_rubric_retry_hint"):
                    messages.append({"role": "user", "content": context["_rubric_retry_hint"]})
                elif rubric_attempt == 2:
                    messages.append({"role": "user", "content": "Switch strategy: try a completely different approach."})
                output = await _react_loop(llm, messages, tool_registry, tool_guard, max_react_iters)
            else:
                skill_context = dict(context)
                if rubric_attempt == 1 and skill_context.get("_rubric_retry_hint"):
                    skill_context["rubric_feedback"] = skill_context["_rubric_retry_hint"]
                elif rubric_attempt == 2:
                    skill_context["rubric_feedback"] = "Switch strategy: try a completely different approach."
                messages = [{"role": "user", "content": user_message}]
                output = await execute_skill(skill, llm, tool_registry, messages, skill_context, max_react_iters, tool_guard=tool_guard)

            rubric_result = await _rubric_gate.check(output, context)
            if rubric_result.verdict == "pass":
                rubric_passed = True
                break
            context["_rubric_retry_hint"] = rubric_result.retry_hint or ""
            rubric_attempt += 1

        context.pop("_rubric_retry_hint", None)

        if not rubric_passed:
            yield ExecutionEvent(EventType.BLOCKED, {"skill": node.skill_name, "reason": rubric_result.reason})
            yield ExecutionEvent(EventType.DONE, {})
            return

        if isinstance(node.gate, LLMGate):
            node.gate.set_llm(llm)
        gate_result = await node.gate.check(output, context)
        yield ExecutionEvent(EventType.GATE_RESULT, {
            "skill": node.skill_name, "verdict": gate_result.verdict, "reason": gate_result.reason,
        })

        if gate_result.verdict == "pass":
            context[f"{node.skill_name}_output"] = output
            # Checkpoint save after each successful skill node
            session_id = str(context.get("session_id") or "")
            profile_dir = str(context.get("_profile_dir") or "")
            if session_id and profile_dir:
                try:
                    from .session_state import SessionStateManager, SessionCheckpoint
                    state_mgr = SessionStateManager(Path(profile_dir))
                    state_mgr.save(SessionCheckpoint(
                        agent_id=str(context.get("agent_id") or ""),
                        session_id=session_id,
                        task_type=str(context.get("task_type") or ""),
                        skill_chain_index=node_idx,
                        context={k: v for k, v in context.items() if not k.startswith("_")},
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ))
                except Exception:
                    logger.exception("failed to save session checkpoint")
            yield ExecutionEvent(EventType.SKILL_END, {"skill": node.skill_name, "status": "passed"})
            node_idx += 1
            continue

        sig = FailureSignature(error_type=node.skill_name, context_hash=hashlib.md5(output.encode()).hexdigest()[:8])
        action = guard.record(sig)

        if action == "blocked":
            yield ExecutionEvent(EventType.BLOCKED, {"skill": node.skill_name, "reason": gate_result.reason})
            yield ExecutionEvent(EventType.DONE, {})
            return

        if action == "switch" and node.skill_name in skill_chain.backtrack_map:
            backtrack_count += 1
            if backtrack_count > max_backtracks:
                yield ExecutionEvent(EventType.BLOCKED, {"skill": node.skill_name, "reason": "max backtracks"})
                yield ExecutionEvent(EventType.DONE, {})
                return
            target = skill_chain.backtrack_map[node.skill_name]
            yield ExecutionEvent(EventType.BACKTRACK, {"from": node.skill_name, "to": target})
            node_idx = next((i for i, n in enumerate(skill_chain.nodes) if n.skill_name == target), 0)
            continue

        yield ExecutionEvent(EventType.SKILL_END, {"skill": node.skill_name, "status": "retry"})

    # Emit final output as text
    for node in reversed(skill_chain.nodes):
        key = f"{node.skill_name}_output"
        if key in context:
            yield ExecutionEvent(EventType.TEXT_DELTA, {"text": context[key]})
            break

    # Clear checkpoint on successful completion
    session_id = str(context.get("session_id") or "")
    profile_dir = str(context.get("_profile_dir") or "")
    if session_id and profile_dir:
        try:
            from .session_state import SessionStateManager
            state_mgr = SessionStateManager(Path(profile_dir))
            state_mgr.clear(session_id)
        except Exception:
            logger.exception("failed to clear session checkpoint")

    yield ExecutionEvent(EventType.DONE, {})


class _AgentSetup(NamedTuple):
    """Prepared prompt/routing state for one engine request."""
    profile_dir: Path
    system_prompt: str
    task_type: TaskType
    chain: SkillChain | None


def _merge_context(user_message: str, context: str | None) -> str:
    """引擎输入 = 用户原文 + 隐式环境上下文；路由和记忆只基于用户原文。"""
    return f"{user_message}\n\n{context}" if context else user_message


def _missing_skill_message(skill_registry: SkillRegistry, forced_skill: str) -> str:
    available = ", ".join(
        sorted(summary["name"] for summary in skill_registry.list_summaries())
    )
    if not available:
        return f"Skill '{forced_skill}' not found. No skills are currently available."
    return (
        f"Skill '{forced_skill}' not found. "
        f"Available skills: {available}"
    )


def _enabled_tools_from_config(emp_config: dict, tool_registry: ToolRegistry) -> list[str]:
    """Resolve the runtime tool allowlist for an agent.

    Missing config means "all registered tools except internal/default-hidden
    tools"; explicit tools.enabled narrows that list further. This keeps stale
    template entries such as search_knowledge from resurfacing.
    """
    available = tool_registry.list_tool_names(include_disabled=True)
    tools_cfg = emp_config.get("tools") if isinstance(emp_config, dict) else {}
    enabled = tools_cfg.get("enabled") if isinstance(tools_cfg, dict) else None
    if not isinstance(enabled, list):
        return [name for name in available if name not in _HIDDEN_DEFAULT_TOOLS]

    return [
        name
        for name in enabled
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
            runtime.agent_id,
            ", ".join(sorted(set(unknown_tools))),
        )

    services.skill_registry.load_builtin(runtime.agents_dir / "skills")
    profile_skills = runtime.profile_dir / "skills"
    if profile_skills.is_dir():
        services.skill_registry.load_agent_skills(profile_skills)

    from engine.memory.store import search_relevant_memories

    retrieved = await search_relevant_memories(runtime.profile_dir, request.message)
    assembler = PromptAssembler()
    system_prompt = assembler.assemble(
        runtime.profile_dir,
        services.tool_registry,
        services.skill_registry,
        _runtime_prompt_context(runtime),
        retrieved_memory=retrieved,
    )

    task_type = route_task(request.message)
    if detect_eval_sensitive(request.message):
        system_prompt += "\n\n" + EVAL_SENSITIVE_GUIDANCE

    chain: SkillChain | None = None
    available_skills = {
        summary["name"] for summary in services.skill_registry.list_summaries()
    }
    if task_type == TaskType.FEATURE:
        chain = SkillChain.feature_chain().for_available_skills(available_skills)
    elif task_type == TaskType.BUGFIX:
        chain = SkillChain.bugfix_chain().for_available_skills(available_skills)

    return _AgentSetup(runtime.profile_dir, system_prompt, task_type, chain)


async def _run_forced_skill_stream(
    llm: LLMClient,
    tool_registry: ToolRegistry,
    skill_registry: SkillRegistry,
    user_message: str,
    forced_skill: str,
    tool_guard: ToolGuard | None,
    max_react_iters: int,
    history: list[dict] | None = None,
) -> AsyncGenerator[ExecutionEvent, None]:
    yield ExecutionEvent(EventType.ROUTE_DECIDED, {"type": "skill", "skill": forced_skill})

    skill = skill_registry.get(forced_skill)
    if skill is None:
        yield ExecutionEvent(EventType.BLOCKED, {
            "skill": forced_skill,
            "reason": _missing_skill_message(skill_registry, forced_skill),
        })
        yield ExecutionEvent(EventType.TEXT_DELTA, {
            "text": _missing_skill_message(skill_registry, forced_skill),
        })
        yield ExecutionEvent(EventType.DONE, {})
        return

    yield ExecutionEvent(EventType.SKILL_START, {"skill": forced_skill, "index": 0})
    messages = [*(history or []), {"role": "user", "content": user_message}]
    context = {"user_message": user_message, "task_type": "skill", "forced_skill": forced_skill}
    output = await execute_skill(
        skill,
        llm,
        tool_registry,
        messages,
        context,
        max_react_iters,
        tool_guard=tool_guard,
    )
    yield ExecutionEvent(EventType.SKILL_END, {"skill": forced_skill, "status": "passed"})
    yield ExecutionEvent(EventType.TEXT_DELTA, {"text": output})
    yield ExecutionEvent(EventType.DONE, {})


async def _persist_runtime_learning(
    runtime: RuntimeContext,
    user_message: str,
    reply_text: str,
    had_tools: bool,
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
    """Keep streaming and non-streaming persistence criteria identical."""
    return event.type in (EventType.TOOL_CALL_START, EventType.SKILL_START)


def _fact_gate_for_request(request: EngineRequest, runtime: RuntimeContext) -> FactGate:
    """Create one isolated preflight state container for this user turn."""

    return FactGate(FactGateContext(
        session_id=runtime.session_id or "",
        turn_id=uuid4().hex,
    ))


async def reply_with_runtime(
    request: EngineRequest,
    runtime: RuntimeContext,
    services: RuntimeServices,
) -> EngineResult:
    """Run one engine request using an explicit runtime contract."""
    s = await prepare_runtime(request, runtime, services)
    guard = FailureLoopGuard()

    try:
        full_text: list[str] = []
        had_tools = False
        with use_fact_gate(_fact_gate_for_request(request, runtime)):
            async for event in run_agent_stream(
                services.llm,
                s.system_prompt,
                _merge_context(request.message, request.context),
                services.tool_registry,
                services.skill_registry,
                s.task_type,
                s.chain,
                guard,
                tool_guard=services.tool_guard,
                history=request.history,
                forced_skill=request.forced_skill,
                execution_context=_runtime_execution_context(runtime),
            ):
                if event.type == EventType.TEXT_DELTA:
                    full_text.append(event.data.get("text", ""))
                elif _has_memory_worthy_activity(event):
                    had_tools = True

        result = "".join(full_text)
        await _persist_runtime_learning(runtime, request.message, result, had_tools)
        return EngineResult(text=result, had_tools=had_tools)
    finally:
        await services.close()


async def reply_events_with_runtime(
    request: EngineRequest,
    runtime: RuntimeContext,
    services: RuntimeServices,
) -> AsyncGenerator[ExecutionEvent, None]:
    """Event-streaming entry point over an explicit runtime contract."""
    s = await prepare_runtime(request, runtime, services)
    guard = FailureLoopGuard()

    full_text = []
    had_tools = False
    try:
        try:
            with use_fact_gate(_fact_gate_for_request(request, runtime)):
                async for event in run_agent_stream(
                    services.llm,
                    s.system_prompt,
                    _merge_context(request.message, request.context),
                    services.tool_registry,
                    services.skill_registry,
                    s.task_type,
                    s.chain,
                    guard,
                    tool_guard=services.tool_guard,
                    history=request.history,
                    forced_skill=request.forced_skill,
                    execution_context=_runtime_execution_context(runtime),
                ):
                    if event.type == EventType.TEXT_DELTA:
                        full_text.append(event.data.get("text", ""))
                    elif _has_memory_worthy_activity(event):
                        had_tools = True
                    yield event
        except Exception as e:
            # 任一环节失败（LLM 超长上下文/网络/工具崩溃）：优雅收尾，SSE 流不裸断。
            # 异常详情只进服务端日志，不透给前端（可能含 base_url / 请求细节）。
            logger.exception("agent execution failed (agent=%s)", runtime.agent_id)
            yield ExecutionEvent(EventType.TEXT_DELTA, {
                "text": f"⚠️ 执行失败：{type(e).__name__}（详情见服务端日志）",
            })
            yield ExecutionEvent(EventType.DONE, {})
    finally:
        full = "".join(full_text)
        await _persist_runtime_learning(runtime, request.message, full, had_tools)
        await services.close()


async def reply(
    agent_id: str, name: str, user_message: str,
    history: list[dict] | None = None,
    context: str | None = None,
    forced_skill: str | None = None,
) -> str:
    """Legacy high-level entry point for agent_id-based callers."""
    from .legacy import reply as legacy_reply

    return await legacy_reply(
        agent_id,
        name,
        user_message,
        history=history,
        context=context,
        forced_skill=forced_skill,
    )


async def reply_events(
    agent_id: str, name: str, user_message: str,
    history: list[dict] | None = None,
    context: str | None = None,
    forced_skill: str | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[ExecutionEvent, None]:
    """Legacy structured event stream for agent_id-based callers."""
    from .legacy import reply_events as legacy_reply_events

    async for event in legacy_reply_events(
        agent_id,
        name,
        user_message,
        history=history,
        context=context,
        forced_skill=forced_skill,
        session_id=session_id,
    ):
        yield event


async def reply_stream_with_runtime(
    request: EngineRequest,
    runtime: RuntimeContext,
    services: RuntimeServices,
) -> AsyncGenerator[str, None]:
    """Text-only stream adapter over reply_events_with_runtime()."""
    async for event in reply_events_with_runtime(request, runtime, services):
        if event.type == EventType.TEXT_DELTA:
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
    agent_id: str,
    name: str,
    user_message: str,
    history: list[dict] | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Legacy text stream for agent_id-based callers."""
    from .legacy import reply_stream as legacy_reply_stream

    async for chunk in legacy_reply_stream(
        agent_id,
        name,
        user_message,
        history=history,
        session_id=session_id,
    ):
        yield chunk

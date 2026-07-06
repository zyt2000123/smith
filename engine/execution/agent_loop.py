from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator, NamedTuple

if TYPE_CHECKING:
    pass

from llm.client import LLMClient
from llm.model_config import build_llm_client
from prompt.assembler import PromptAssembler
from safety.tool_guard import ToolGuard
from skill.executor import execute_skill
from skill.registry import SkillRegistry
from tool.interface import ToolCall
from tool.registry import ToolRegistry
from .backtrack import FailureLoopGuard, FailureSignature
from .events import EventType, ExecutionEvent
from .gate import LLMGate, SkillRubricGate
from .skill_chain import SkillChain
from .task_router import (
    EVAL_SENSITIVE_GUIDANCE,
    TaskType,
    detect_eval_sensitive,
    route_task,
)

# Shared rubric gate instance — stateless, safe to reuse
_rubric_gate = SkillRubricGate()
_RUBRIC_MAX_RETRIES = 3

logger = logging.getLogger(__name__)


async def _react_loop(
    llm: LLMClient,
    messages: list[dict],
    tool_registry: ToolRegistry,
    tool_guard: ToolGuard | None = None,
    max_iters: int = 20,
) -> str:
    """Simple ReAct loop: think -> act -> observe, until no tool calls."""
    tools = tool_registry.get_schemas() or None
    conversation = list(messages)
    consecutive_errors = 0

    for _ in range(max_iters):
        # Sliding window: keep system prompt + last 30 messages
        if len(conversation) > 40:
            conversation = [conversation[0]] + conversation[-30:]

        response = await llm.chat(conversation, tools=tools)

        if not response.has_tool_calls:
            return response.text

        conversation.append({
            "role": "assistant",
            "content": response.text,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                }
                for tc in response.tool_calls
            ],
        })

        for tc in response.tool_calls:
            call = ToolCall(id=tc.id, name=tc.name, arguments=tc.arguments)

            # Safety guard: check before executing
            if tool_guard is not None:
                guard_result = tool_guard.check(call)
                if not guard_result.allowed:
                    conversation.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": f"[BLOCKED] {guard_result.reason}",
                    })
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        conversation.append({"role": "system", "content":
                            "Multiple tool calls have failed consecutively. Change your approach — try a different tool, simplify the command, or explain what you need without using tools."})
                        consecutive_errors = 0
                    continue

            result = await tool_registry.execute(call)
            conversation.append({
                "role": "tool",
                "tool_call_id": result.call_id,
                "content": result.content,
            })
            if result.is_error:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    conversation.append({"role": "system", "content":
                        "Multiple tool calls have failed consecutively. Change your approach — try a different tool, simplify the command, or explain what you need without using tools."})
                    consecutive_errors = 0
            else:
                consecutive_errors = 0

    return "Max ReAct iterations reached."


async def _react_stream_loop(
    llm: LLMClient,
    messages: list[dict],
    tool_registry: ToolRegistry,
    tool_guard: ToolGuard | None = None,
    max_iters: int = 20,
) -> AsyncGenerator[str, None]:
    """Streaming ReAct loop: run tool calls synchronously, stream the final text response."""
    tools = tool_registry.get_schemas() or None
    conversation = list(messages)

    for _ in range(max_iters):
        response = await llm.chat(conversation, tools=tools)

        if not response.has_tool_calls:
            # Final response — re-issue as streaming call (without tools to avoid tool_calls)
            async for chunk in llm.chat_stream(conversation):
                yield chunk
            return

        # Tool-calling iteration — same as non-streaming
        conversation.append({
            "role": "assistant",
            "content": response.text,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                }
                for tc in response.tool_calls
            ],
        })

        for tc in response.tool_calls:
            call = ToolCall(id=tc.id, name=tc.name, arguments=tc.arguments)

            # Safety guard: check before executing
            if tool_guard is not None:
                guard_result = tool_guard.check(call)
                if not guard_result.allowed:
                    conversation.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": f"[BLOCKED] {guard_result.reason}",
                    })
                    continue

            result = await tool_registry.execute(call)
            conversation.append({
                "role": "tool",
                "tool_call_id": result.call_id,
                "content": result.content,
            })

    yield "Max ReAct iterations reached."


async def _react_event_loop(
    llm: LLMClient,
    messages: list[dict],
    tool_registry: ToolRegistry,
    tool_guard: ToolGuard | None = None,
    max_iters: int = 20,
) -> AsyncGenerator[ExecutionEvent, None]:
    """ReAct loop that yields structured ExecutionEvents."""
    tools = tool_registry.get_schemas() or None
    conversation = list(messages)
    consecutive_errors = 0

    for _ in range(max_iters):
        if len(conversation) > 40:
            conversation = [conversation[0]] + conversation[-30:]

        yield ExecutionEvent(EventType.THINKING, {})
        response = await llm.chat(conversation, tools=tools)

        # 思考内容：优先思考模型的 reasoning_content；工具轮退回前导推理文本
        thought = (response.reasoning or (response.text if response.has_tool_calls else "")).strip()
        if thought:
            yield ExecutionEvent(EventType.THINKING, {"text": thought, "done": True})

        if not response.has_tool_calls:
            # 最终回答：重发为流式调用（不带 tools，避免再触发 tool_calls），逐块透出
            streamed_any = False
            try:
                async for chunk in llm.chat_stream(conversation):
                    streamed_any = True
                    yield ExecutionEvent(EventType.TEXT_DELTA, {"text": chunk})
            except Exception:
                pass
            if not streamed_any:
                yield ExecutionEvent(EventType.TEXT_DELTA, {"text": response.text})
            return

        conversation.append({
            "role": "assistant",
            "content": response.text,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                for tc in response.tool_calls
            ],
        })

        for tc in response.tool_calls:
            call = ToolCall(id=tc.id, name=tc.name, arguments=tc.arguments)
            yield ExecutionEvent(EventType.TOOL_CALL_START, {"name": tc.name, "id": tc.id})

            if tool_guard is not None:
                guard_result = tool_guard.check(call)
                if not guard_result.allowed:
                    conversation.append({"role": "tool", "tool_call_id": call.id,
                                         "content": f"[BLOCKED] {guard_result.reason}"})
                    yield ExecutionEvent(EventType.TOOL_CALL_RESULT, {"id": tc.id, "blocked": True, "reason": guard_result.reason})
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        conversation.append({"role": "system", "content": "Multiple tool calls failed. Change your approach."})
                        consecutive_errors = 0
                    continue

            result = await tool_registry.execute(call)
            conversation.append({"role": "tool", "tool_call_id": result.call_id, "content": result.content})
            yield ExecutionEvent(EventType.TOOL_CALL_RESULT, {
                "id": tc.id, "error": result.is_error, "content": result.content[:200],
            })
            if result.is_error:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    conversation.append({"role": "system", "content": "Multiple tool calls failed. Change your approach."})
                    consecutive_errors = 0
            else:
                consecutive_errors = 0

    yield ExecutionEvent(EventType.TEXT_DELTA, {"text": "Max ReAct iterations reached."})


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
    max_react_iters: int = 20,
    history: list[dict] | None = None,
) -> AsyncGenerator[ExecutionEvent, None]:
    """Streaming version of run_agent — yields ExecutionEvents throughout execution."""
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
            try:
                from .session_state import SessionStateManager, SessionCheckpoint
                state_mgr = SessionStateManager(Path(context.get("_employee_dir", "")))
                state_mgr.save(SessionCheckpoint(
                    employee_id=context.get("employee_id", ""),
                    session_id=context.get("session_id", ""),
                    task_type=context.get("task_type", ""),
                    skill_chain_index=node_idx,
                    context={k: v for k, v in context.items() if not k.startswith("_")},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))
            except Exception:
                pass
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
    try:
        from .session_state import SessionStateManager
        state_mgr = SessionStateManager(Path(context.get("_employee_dir", "")))
        state_mgr.clear(context.get("session_id", ""))
    except Exception:
        pass

    yield ExecutionEvent(EventType.DONE, {})


async def run_agent(
    llm: LLMClient,
    system_prompt: str,
    user_message: str,
    tool_registry: ToolRegistry,
    skill_registry: SkillRegistry,
    task_type: TaskType,
    skill_chain: SkillChain | None,
    guard: FailureLoopGuard,
    tool_guard: ToolGuard | None = None,
    max_react_iters: int = 20,
    history: list[dict] | None = None,
) -> str:
    """Orchestrate the full agent flow.

    DIRECT tasks run a simple ReAct loop.
    BUGFIX/FEATURE tasks iterate through a skill chain with gates and backtracking.
    """
    base_messages = [
        {"role": "system", "content": system_prompt},
        *(history or []),
        {"role": "user", "content": user_message},
    ]

    # --- Direct mode ---
    if task_type == TaskType.DIRECT or skill_chain is None:
        return await _react_loop(llm, base_messages, tool_registry, tool_guard, max_react_iters)

    # --- Skill chain mode ---
    context: dict = {"user_message": user_message, "task_type": task_type.value}
    node_idx = 0
    max_backtracks = 5
    backtrack_count = 0

    while node_idx < len(skill_chain.nodes):
        node = skill_chain.nodes[node_idx]

        # Check skip condition
        if node.condition is not None and not node.condition(context):
            node_idx += 1
            continue

        # --- Execute skill with rubric gate retry loop ---
        rubric_attempt = 0
        output = ""
        rubric_passed = False

        while rubric_attempt < _RUBRIC_MAX_RETRIES:
            # Build messages — may include rubric retry hints
            skill = skill_registry.get(node.skill_name)
            if skill is None:
                messages = base_messages + [
                    {"role": "user", "content": f"[Skill: {node.skill_name}] {user_message}"},
                ]
                if rubric_attempt == 1 and context.get("_rubric_retry_hint"):
                    messages.append({"role": "user", "content": context["_rubric_retry_hint"]})
                elif rubric_attempt == 2:
                    messages.append({"role": "user", "content": "Switch strategy: try a completely different approach to address the task."})
                output = await _react_loop(llm, messages, tool_registry, tool_guard, max_react_iters)
            else:
                skill_context = dict(context)
                if rubric_attempt == 1 and skill_context.get("_rubric_retry_hint"):
                    skill_context["rubric_feedback"] = skill_context["_rubric_retry_hint"]
                elif rubric_attempt == 2:
                    skill_context["rubric_feedback"] = "Switch strategy: try a completely different approach to address the task."
                messages = [{"role": "user", "content": user_message}]
                output = await execute_skill(skill, llm, tool_registry, messages, skill_context, max_react_iters, tool_guard=tool_guard)

            # Rubric gate check (before node's own gate)
            rubric_result = await _rubric_gate.check(output, context)
            if rubric_result.verdict == "pass":
                rubric_passed = True
                break

            # Store hint for next retry
            context["_rubric_retry_hint"] = rubric_result.retry_hint or ""
            rubric_attempt += 1

        # Clean up transient rubric keys
        context.pop("_rubric_retry_hint", None)

        if not rubric_passed:
            return (
                f"Blocked: skill '{node.skill_name}' failed rubric gate after "
                f"{_RUBRIC_MAX_RETRIES} attempts. Last: {rubric_result.reason}"
            )

        # --- Node gate check (existing logic, unchanged) ---
        if isinstance(node.gate, LLMGate):
            node.gate.set_llm(llm)
        gate_result = await node.gate.check(output, context)

        if gate_result.verdict == "pass":
            context[f"{node.skill_name}_output"] = output
            node_idx += 1
            continue

        # Gate failed — consult loop guard
        sig = FailureSignature(
            error_type=node.skill_name,
            context_hash=hashlib.md5(output.encode()).hexdigest()[:8],
        )
        action = guard.record(sig)

        if action == "blocked":
            return (
                f"Blocked: repeated failures at '{node.skill_name}'. "
                f"Last gate: {gate_result.reason}"
            )

        if action == "switch" and node.skill_name in skill_chain.backtrack_map:
            backtrack_count += 1
            if backtrack_count > max_backtracks:
                return f"Max backtracks exceeded at '{node.skill_name}'."
            target = skill_chain.backtrack_map[node.skill_name]
            node_idx = next(
                (i for i, n in enumerate(skill_chain.nodes) if n.skill_name == target),
                0,
            )
            continue

        # Retry — stay on same node (loop guard will eventually block)

    # Collect final output from last completed skill
    for node in reversed(skill_chain.nodes):
        if f"{node.skill_name}_output" in context:
            return context[f"{node.skill_name}_output"]

    return "Skill chain completed with no output."


class _AgentSetup(NamedTuple):
    """reply()/reply_events() 的公共装配结果。"""
    llm: LLMClient
    tool_registry: ToolRegistry
    skill_registry: SkillRegistry
    employee_dir: Path
    system_prompt: str
    task_type: TaskType
    chain: SkillChain | None
    tool_guard: ToolGuard


def _merge_context(user_message: str, context: str | None) -> str:
    """引擎输入 = 用户原文 + 隐式环境上下文；路由和记忆只基于用户原文。"""
    return f"{user_message}\n\n{context}" if context else user_message


async def _prepare(employee_id: str, name: str, user_message: str) -> _AgentSetup:
    """Shared setup: build LLM, registries, MCP tools, prompt, and route the task."""
    # Import here to avoid circular deps at module level
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from common.config_loader import resolve_llm_config
    from common.config import DATA_DIR, SAFETY_RULES_PATH

    llm = build_llm_client(resolve_llm_config(employee_id))

    tool_registry = ToolRegistry()
    skill_registry = SkillRegistry()
    employee_dir = DATA_DIR / "employees" / employee_id

    agents_dir = Path(__file__).resolve().parents[2] / "agents"
    tool_registry.load_providers(agents_dir / "tools")

    # Load MCP servers from employee config (if any)
    try:
        from common.yaml_utils import load_yaml
        emp_config = load_yaml(employee_dir / "config.yaml")
        mcp_servers = emp_config.get("mcp_servers", [])
        if mcp_servers:
            from tool.mcp_client import MCPClient, register_mcp_tools
            for srv in mcp_servers:
                cmd = srv.get("command", [])
                if cmd:
                    client = MCPClient(cmd, env=srv.get("env"))
                    await client.connect()
                    await register_mcp_tools(tool_registry, client)
    except Exception:
        pass  # MCP is best-effort

    skill_registry.load_builtin(agents_dir / "skills")
    emp_skills = employee_dir / "skills"
    if emp_skills.is_dir():
        skill_registry.load_employee_skills(emp_skills)

    # Assemble prompt (with query-time memory retrieval)
    from memory.store import search_relevant_memories
    retrieved = await search_relevant_memories(employee_dir, user_message)
    assembler = PromptAssembler()
    context = {"employee_id": employee_id, "name": name, "_employee_dir": str(employee_dir)}
    system_prompt = assembler.assemble(
        employee_dir, tool_registry, skill_registry, context, retrieved_memory=retrieved,
    )

    task_type = route_task(user_message)
    if detect_eval_sensitive(user_message):
        system_prompt += "\n\n" + EVAL_SENSITIVE_GUIDANCE

    chain: SkillChain | None = None
    if task_type == TaskType.FEATURE:
        chain = SkillChain.feature_chain()
    elif task_type == TaskType.BUGFIX:
        chain = SkillChain.bugfix_chain()

    return _AgentSetup(
        llm, tool_registry, skill_registry, employee_dir,
        system_prompt, task_type, chain, ToolGuard(SAFETY_RULES_PATH),
    )


async def reply(
    employee_id: str, name: str, user_message: str,
    history: list[dict] | None = None, context: str | None = None,
) -> str:
    """High-level entry point for the server layer.

    *history*: recent session messages ({"role","content"}) for short-term context.
    *context*: implicit environment context (workdir/attachments) — visible to the
    LLM only; routing and memory persistence use the raw user message.
    """
    s = await _prepare(employee_id, name, user_message)
    guard = FailureLoopGuard()

    try:
        result = await run_agent(
            s.llm, s.system_prompt, _merge_context(user_message, context),
            s.tool_registry, s.skill_registry,
            s.task_type, s.chain, guard,
            tool_guard=s.tool_guard,
            history=history,
        )

        # Save conversation memory + learn preferences (best-effort, never break the reply)
        try:
            from memory.store import save_conversation_memory
            await save_conversation_memory(s.employee_dir, user_message, result, True)

            from memory.user_learner import UserPreferenceLearner
            learner = UserPreferenceLearner(s.employee_dir)
            await learner.observe(user_message, result)
        except Exception:
            pass

        return result
    finally:
        await s.llm.close()


async def reply_events(
    employee_id: str, name: str, user_message: str,
    history: list[dict] | None = None, context: str | None = None,
) -> AsyncGenerator[ExecutionEvent, None]:
    """Event-streaming entry point: yields structured ExecutionEvents
    (thinking / tool_call / text_delta / skill / done...) for Agent-style UIs."""
    s = await _prepare(employee_id, name, user_message)
    guard = FailureLoopGuard()

    full_text = []
    had_tools = False
    try:
        try:
            async for event in run_agent_stream(
                s.llm, s.system_prompt, _merge_context(user_message, context),
                s.tool_registry, s.skill_registry,
                s.task_type, s.chain, guard,
                tool_guard=s.tool_guard,
                history=history,
            ):
                if event.type == EventType.TEXT_DELTA:
                    full_text.append(event.data.get("text", ""))
                elif event.type in (EventType.TOOL_CALL_START, EventType.SKILL_START):
                    had_tools = True
                yield event
        except Exception as e:
            # 任一环节失败（LLM 超长上下文/网络/工具崩溃）：优雅收尾，SSE 流不裸断。
            # 异常详情只进服务端日志，不透给前端（可能含 base_url / 请求细节）。
            logger.exception("agent execution failed (employee=%s)", employee_id)
            yield ExecutionEvent(EventType.TEXT_DELTA, {
                "text": f"⚠️ 执行失败：{type(e).__name__}（详情见服务端日志）",
            })
            yield ExecutionEvent(EventType.DONE, {})
    finally:
        full = "".join(full_text)
        try:
            from memory.store import save_conversation_memory
            await save_conversation_memory(s.employee_dir, user_message, full, had_tools)
        except Exception:
            pass  # memory persistence must never break the stream teardown
        try:
            from memory.user_learner import UserPreferenceLearner
            learner = UserPreferenceLearner(s.employee_dir)
            await learner.observe(user_message, full)
        except Exception:
            pass  # learning must never break the stream teardown
        await s.llm.close()


async def reply_stream(
    employee_id: str, name: str, user_message: str, history: list[dict] | None = None
) -> AsyncGenerator[str, None]:
    """Streaming version of reply(). Yields text chunks as they arrive.

    Thin adapter over reply_events() — kept for callers that only need text
    (e.g. team_service group chat)."""
    async for event in reply_events(employee_id, name, user_message, history=history):
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

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator

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
from .gate import SkillRubricGate
from .skill_chain import SkillChain
from .task_router import TaskType, route_task

# Shared rubric gate instance — stateless, safe to reuse
_rubric_gate = SkillRubricGate()
_RUBRIC_MAX_RETRIES = 3


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

    for _ in range(max_iters):
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
                    continue

            result = await tool_registry.execute(call)
            conversation.append({
                "role": "tool",
                "tool_call_id": result.call_id,
                "content": result.content,
            })

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
) -> str:
    """Orchestrate the full agent flow.

    DIRECT tasks run a simple ReAct loop.
    BUGFIX/FEATURE tasks iterate through a skill chain with gates and backtracking.
    """
    base_messages = [
        {"role": "system", "content": system_prompt},
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


async def reply(employee_id: str, name: str, user_message: str) -> str:
    """High-level entry point for the server layer.

    Builds LLM client from config, assembles prompt, routes task, and runs.
    """
    # Import here to avoid circular deps at module level
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from common.config_loader import resolve_llm_config
    from common.config import DATA_DIR, SAFETY_RULES_PATH

    # Build LLM
    llm_cfg = resolve_llm_config(employee_id)
    llm = build_llm_client(llm_cfg)

    # Set up registries
    tool_registry = ToolRegistry()
    skill_registry = SkillRegistry()

    employee_dir = DATA_DIR / "employees" / employee_id

    # Load tools + skills
    tools_dir = Path(__file__).resolve().parents[2] / "agents" / "tools"
    tool_registry.load_providers(tools_dir)

    skills_dir = Path(__file__).resolve().parents[2] / "agents" / "skills"
    skill_registry.load_builtin(skills_dir)
    emp_skills = employee_dir / "skills"
    if emp_skills.is_dir():
        skill_registry.load_employee_skills(emp_skills)

    # Assemble prompt
    assembler = PromptAssembler()
    context = {"employee_id": employee_id, "name": name}
    system_prompt = assembler.assemble(employee_dir, tool_registry, skill_registry, context)

    # Route and run
    task_type = route_task(user_message)
    chain: SkillChain | None = None
    if task_type == TaskType.FEATURE:
        chain = SkillChain.feature_chain()
    elif task_type == TaskType.BUGFIX:
        chain = SkillChain.bugfix_chain()

    guard = FailureLoopGuard()
    tool_guard = ToolGuard(SAFETY_RULES_PATH)

    try:
        result = await run_agent(
            llm, system_prompt, user_message,
            tool_registry, skill_registry,
            task_type, chain, guard,
            tool_guard=tool_guard,
        )

        # Save conversation memory for non-trivial tasks
        had_tools = task_type != TaskType.DIRECT
        from memory.store import save_conversation_memory
        await save_conversation_memory(employee_dir, user_message, result, had_tools)

        # Learn user preferences from conversation
        from memory.user_learner import UserPreferenceLearner
        learner = UserPreferenceLearner(employee_dir)
        await learner.observe(user_message, result)

        return result
    finally:
        await llm.close()


async def reply_stream(employee_id: str, name: str, user_message: str) -> AsyncGenerator[str, None]:
    """Streaming version of reply(). Yields text chunks as they arrive."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from common.config_loader import resolve_llm_config
    from common.config import DATA_DIR, SAFETY_RULES_PATH

    llm_cfg = resolve_llm_config(employee_id)
    llm = build_llm_client(llm_cfg)

    tool_registry = ToolRegistry()
    skill_registry = SkillRegistry()

    employee_dir = DATA_DIR / "employees" / employee_id

    tools_dir = Path(__file__).resolve().parents[2] / "agents" / "tools"
    tool_registry.load_providers(tools_dir)

    skills_dir = Path(__file__).resolve().parents[2] / "agents" / "skills"
    skill_registry.load_builtin(skills_dir)
    emp_skills = employee_dir / "skills"
    if emp_skills.is_dir():
        skill_registry.load_employee_skills(emp_skills)

    assembler = PromptAssembler()
    context = {"employee_id": employee_id, "name": name}
    system_prompt = assembler.assemble(employee_dir, tool_registry, skill_registry, context)

    task_type = route_task(user_message)
    tool_guard = ToolGuard(SAFETY_RULES_PATH)

    try:
        if task_type == TaskType.DIRECT:
            base_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            async for chunk in _react_stream_loop(llm, base_messages, tool_registry, tool_guard):
                yield chunk
        else:
            # Skill chain — fall back to non-streaming
            chain: SkillChain | None = None
            if task_type == TaskType.FEATURE:
                chain = SkillChain.feature_chain()
            elif task_type == TaskType.BUGFIX:
                chain = SkillChain.bugfix_chain()
            guard = FailureLoopGuard()
            result = await run_agent(
                llm, system_prompt, user_message,
                tool_registry, skill_registry,
                task_type, chain, guard,
                tool_guard=tool_guard,
            )
            yield result
    finally:
        from memory.user_learner import UserPreferenceLearner
        learner = UserPreferenceLearner(employee_dir)
        await learner.observe(user_message, "")
        await llm.close()

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.llm.client import LLMClient
    from engine.tool.registry import ToolRegistry
    from engine.safety.tool_guard import ToolGuard

from .loader import SkillBody
from tool.interface import ToolCall


async def execute_skill(
    skill: SkillBody,
    llm: "LLMClient",
    tool_registry: "ToolRegistry",
    messages: list[dict],
    context: dict,
    max_iters: int = 20,
    tool_guard: "ToolGuard | None" = None,
) -> str:
    """Inject SKILL.md content into prompt and run a ReAct loop.

    Returns the final assistant text output.
    """
    skill_system = (
        f"# Skill: {skill.meta.name}\n\n"
        f"{skill.content}\n\n"
        f"Context: {context}"
    )

    conversation: list[dict] = [
        {"role": "system", "content": skill_system},
        *messages,
    ]
    tools = tool_registry.get_schemas()

    for _ in range(max_iters):
        response = await llm.chat(conversation, tools=tools or None)

        if not response.has_tool_calls:
            return response.text

        # Append assistant message with tool calls
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

        # Execute each tool call and append results
        for tc in response.tool_calls:
            call = ToolCall(id=tc.id, name=tc.name, arguments=tc.arguments)

            # Safety guard: check before executing (same pattern as _react_loop)
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

    return conversation[-1].get("content", "Max iterations reached.")

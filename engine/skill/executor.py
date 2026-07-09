from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.llm.client import LLMClient
    from engine.tool.registry import ToolRegistry
    from engine.safety.tool_guard import ToolGuard

from .loader import SkillBody
from engine.execution.react_loop import react_loop
from engine.react_budget import DEFAULT_MAX_REACT_ITERS


async def execute_skill(
    skill: SkillBody,
    llm: "LLMClient",
    tool_registry: "ToolRegistry",
    messages: list[dict],
    context: dict,
    max_iters: int = DEFAULT_MAX_REACT_ITERS,
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
    return await react_loop(llm, conversation, tool_registry, tool_guard, max_iters)

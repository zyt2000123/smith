from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

if TYPE_CHECKING:
    from engine.llm.port import LLMPort
    from engine.tool.registry import ToolRegistry
    from engine.safety.tool_guard import ToolGuard

from .loader import SkillBody
from engine.execution.events import ExecutionEvent
from engine.execution.react_loop import react_event_loop, react_loop
from engine.react_budget import DEFAULT_MAX_REACT_ITERS


async def execute_skill(
    skill: SkillBody,
    llm: "LLMPort",
    tool_registry: "ToolRegistry",
    messages: list[dict],
    context: dict,
    max_iters: int = DEFAULT_MAX_REACT_ITERS,
    tool_guard: "ToolGuard | None" = None,
) -> str:
    """Inject SKILL.md content into prompt and run a ReAct loop.

    Returns the final assistant text output.
    """
    conversation = _skill_conversation(skill, messages, context)
    return await react_loop(llm, conversation, tool_registry, tool_guard, max_iters)


async def execute_skill_events(
    skill: SkillBody,
    llm: "LLMPort",
    tool_registry: "ToolRegistry",
    messages: list[dict],
    context: dict,
    max_iters: int = DEFAULT_MAX_REACT_ITERS,
    tool_guard: "ToolGuard | None" = None,
    provisional_lifecycle: bool = True,
) -> AsyncGenerator[ExecutionEvent, None]:
    """Run a skill through the canonical event stream instead of a text adapter."""
    conversation = _skill_conversation(skill, messages, context)
    async for event in react_event_loop(
        llm,
        conversation,
        tool_registry,
        tool_guard,
        max_iters,
        provisional_lifecycle=provisional_lifecycle,
    ):
        yield event


def _skill_conversation(skill: SkillBody, messages: list[dict], context: dict) -> list[dict]:
    skill_system = (
        f"# Skill: {skill.meta.name}\n\n"
        f"{skill.content}\n\n"
        f"Context: {context}"
    )
    return [
        {"role": "system", "content": skill_system},
        *messages,
    ]

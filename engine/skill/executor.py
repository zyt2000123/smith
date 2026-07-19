from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, Coroutine

if TYPE_CHECKING:
    from engine.observability import ExecutionEvent
    from engine.llm.port import LLMPort
    from engine.tool.registry import ToolRegistry
    from engine.safety.tool_guard import ToolGuard

from .loader import SkillBody
from engine.react_budget import DEFAULT_MAX_REACT_ITERS

# Type aliases for the injected react loop functions.  Callers in
# engine.execution (which already import both packages) pass the real
# implementations — this keeps skill/ free from any execution/ import.
ReactLoopFn = Callable[..., Coroutine[Any, Any, str]]
ReactEventLoopFn = Callable[..., AsyncGenerator["ExecutionEvent", None]]


async def execute_skill(
    skill: SkillBody,
    llm: "LLMPort",
    tool_registry: "ToolRegistry",
    messages: list[dict],
    context: dict,
    max_iters: int = DEFAULT_MAX_REACT_ITERS,
    tool_guard: "ToolGuard | None" = None,
    *,
    react_loop_fn: ReactLoopFn | None = None,
) -> str:
    """Inject SKILL.md content into prompt and run a ReAct loop.

    Returns the final assistant text output.

    ``react_loop_fn`` is the concrete react-loop implementation injected
    by the caller (usually ``engine.execution.react_loop.react_loop``).
    """
    if react_loop_fn is None:
        raise TypeError("react_loop_fn is required — caller must inject the react loop implementation")
    conversation = _skill_conversation(skill, messages, context)
    return await react_loop_fn(llm, conversation, tool_registry, tool_guard, max_iters)


async def execute_skill_events(
    skill: SkillBody,
    llm: "LLMPort",
    tool_registry: "ToolRegistry",
    messages: list[dict],
    context: dict,
    max_iters: int = DEFAULT_MAX_REACT_ITERS,
    tool_guard: "ToolGuard | None" = None,
    provisional_lifecycle: bool = True,
    *,
    react_event_loop_fn: ReactEventLoopFn | None = None,
) -> AsyncGenerator["ExecutionEvent", None]:
    """Run a skill through the canonical event stream instead of a text adapter.

    ``react_event_loop_fn`` is the concrete event-loop implementation
    injected by the caller (usually ``engine.execution.react_loop.react_event_loop``).
    """
    if react_event_loop_fn is None:
        raise TypeError("react_event_loop_fn is required — caller must inject the react event loop implementation")
    conversation = _skill_conversation(skill, messages, context)
    async for event in react_event_loop_fn(
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

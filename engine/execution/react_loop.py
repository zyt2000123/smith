"""Canonical ReAct loop shared by text, stream, and skill execution paths."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, AsyncGenerator

from engine.react_budget import (
    DEFAULT_MAX_REACT_ITERS,
    INCOMPLETE_FINAL_AFTER_TOOL_HINT,
    MAX_FAILED_TOOL_RECOVERY_ITERS,
    MAX_INCOMPLETE_FINAL_REPAIRS,
    MAX_PREFLIGHT_CHALLENGE_ITERS,
    PREFLIGHT_BUDGET_MESSAGE,
    TOOL_CALL_BUDGET_MESSAGE,
    TOOL_FAILURE_BUDGET_MESSAGE,
    TOOL_FAILURE_HINT,
    budget_exhausted_message,
    looks_like_incomplete_final_after_tool,
)
from engine.safety.tool_policy import ToolPolicy
from engine.safety.fact_gate import FactGate, current_fact_gate
from engine.tool.interface import ToolCall

from .compression import compress
from .events import EventType, ExecutionEvent

if TYPE_CHECKING:
    from engine.llm.client import LLMClient
    from engine.safety.tool_guard import ToolGuard
    from engine.tool.registry import ToolRegistry


def _usage_event_data(usage: dict | None) -> dict | None:
    if not isinstance(usage, dict):
        return None

    def number(*keys: str) -> int:
        for key in keys:
            value = usage.get(key)
            if isinstance(value, (int, float)) and value >= 0:
                return int(value)
        return 0

    input_tokens = number("prompt_tokens", "input_tokens")
    output_tokens = number("completion_tokens", "output_tokens")
    total_tokens = number("total_tokens")
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens

    if input_tokens == 0 and output_tokens == 0 and total_tokens == 0:
        return None

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _should_repair_incomplete_final(
    text: str,
    *,
    had_successful_tool: bool,
    repair_count: int,
) -> bool:
    return (
        had_successful_tool
        and repair_count < MAX_INCOMPLETE_FINAL_REPAIRS
        and looks_like_incomplete_final_after_tool(text)
    )


def _append_incomplete_final_repair(conversation: list[dict], text: str) -> None:
    conversation.append({"role": "assistant", "content": text})
    conversation.append({"role": "system", "content": INCOMPLETE_FINAL_AFTER_TOOL_HINT})


async def react_loop(
    llm: "LLMClient",
    messages: list[dict],
    tool_registry: "ToolRegistry",
    tool_guard: "ToolGuard | None" = None,
    max_iters: int = DEFAULT_MAX_REACT_ITERS,
    *,
    fact_gate: FactGate | None = None,
) -> str:
    """Run the canonical ReAct event loop and collect final assistant text."""
    chunks: list[str] = []
    async for event in react_event_loop(
        llm,
        messages,
        tool_registry,
        tool_guard,
        max_iters,
        fact_gate=fact_gate,
    ):
        if event.type == EventType.TEXT_DELTA:
            chunks.append(str(event.data.get("text", "")))
    return "".join(chunks)


async def react_stream_loop(
    llm: "LLMClient",
    messages: list[dict],
    tool_registry: "ToolRegistry",
    tool_guard: "ToolGuard | None" = None,
    max_iters: int = DEFAULT_MAX_REACT_ITERS,
    *,
    fact_gate: FactGate | None = None,
) -> AsyncGenerator[str, None]:
    """Run the canonical ReAct event loop and expose text deltas only."""
    async for event in react_event_loop(
        llm,
        messages,
        tool_registry,
        tool_guard,
        max_iters,
        fact_gate=fact_gate,
    ):
        if event.type == EventType.TEXT_DELTA:
            text = event.data.get("text", "")
            if text:
                yield str(text)


async def react_event_loop(
    llm: "LLMClient",
    messages: list[dict],
    tool_registry: "ToolRegistry",
    tool_guard: "ToolGuard | None" = None,
    max_iters: int = DEFAULT_MAX_REACT_ITERS,
    *,
    fact_gate: FactGate | None = None,
) -> AsyncGenerator[ExecutionEvent, None]:
    """ReAct loop: model response, tool calls, results, and next turn in one history."""
    tools = tool_registry.get_schemas() or None
    # 逐条浅拷贝：prune/compress 会原地改写 content，
    # 不复制会污染调用方传入的 history dict（跨请求复用时留脏数据）。
    conversation = [dict(m) for m in messages]
    policy = ToolPolicy(
        tool_guard,
        fact_gate=fact_gate if fact_gate is not None else current_fact_gate(),
    )
    consecutive_errors = 0
    productive_iters = 0
    recovery_iters = 0
    preflight_iters = 0
    had_successful_tool = False
    incomplete_final_repairs = 0

    while productive_iters < max_iters:
        conversation = await compress(conversation, llm)
        if len(conversation) > 40:
            conversation = [conversation[0]] + conversation[-30:]

        yield ExecutionEvent(EventType.THINKING, {})
        response = await llm.chat(conversation, tools=tools)
        usage = _usage_event_data(response.usage)
        if usage:
            yield ExecutionEvent(EventType.TOKEN_USAGE, usage)

        thought = (response.reasoning or (response.text if response.has_tool_calls else "")).strip()
        if thought:
            yield ExecutionEvent(EventType.THINKING, {"text": thought, "done": True})

        if not response.has_tool_calls:
            if _should_repair_incomplete_final(
                response.text,
                had_successful_tool=had_successful_tool,
                repair_count=incomplete_final_repairs,
            ):
                incomplete_final_repairs += 1
                _append_incomplete_final_repair(conversation, response.text)
                continue
            if response.text:
                yield ExecutionEvent(EventType.TEXT_DELTA, {"text": response.text})
            return

        policy.begin_round()
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

        round_had_success = False
        round_had_failure = False
        round_had_preflight = False
        for tc in response.tool_calls:
            call = ToolCall(id=tc.id, name=tc.name, arguments=tc.arguments)
            yield ExecutionEvent(EventType.TOOL_CALL_START, {"name": tc.name, "id": tc.id, "arguments": tc.arguments})

            decision = policy.evaluate(call)
            if not decision.allowed:
                conversation.append({"role": "tool", "tool_call_id": call.id, "content": decision.observation})
                if decision.challenged:
                    yield ExecutionEvent(EventType.TOOL_CALL_RESULT, {
                        "id": tc.id,
                        "error": False,
                        "blocked": False,
                        "preflight": True,
                        "reason": decision.reason,
                        "level": decision.level.value,
                    })
                    round_had_preflight = True
                    continue
                yield ExecutionEvent(EventType.TOOL_CALL_RESULT, {
                    "id": tc.id,
                    "error": False,
                    "blocked": True,
                    "preflight": False,
                    "reason": decision.reason,
                    "level": decision.level.value,
                    "needs_confirmation": decision.needs_confirmation,
                })
                round_had_failure = True
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    conversation.append({"role": "system", "content": TOOL_FAILURE_HINT})
                    consecutive_errors = 0
                continue

            result = await tool_registry.execute(call)
            conversation.append({"role": "tool", "tool_call_id": result.call_id, "content": result.content})
            yield ExecutionEvent(EventType.TOOL_CALL_RESULT, {
                "id": tc.id,
                "error": result.is_error,
                "blocked": False,
                "preflight": False,
                "content": result.content[:200],
            })
            if result.is_error:
                round_had_failure = True
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    conversation.append({"role": "system", "content": TOOL_FAILURE_HINT})
                    consecutive_errors = 0
            else:
                round_had_success = True
                had_successful_tool = True
                consecutive_errors = 0

        if round_had_preflight:
            preflight_iters += 1
            if preflight_iters >= MAX_PREFLIGHT_CHALLENGE_ITERS:
                yield ExecutionEvent(
                    EventType.TEXT_DELTA,
                    {"text": budget_exhausted_message(PREFLIGHT_BUDGET_MESSAGE)},
                )
                return

        if round_had_success:
            productive_iters += 1
            continue

        if round_had_failure:
            recovery_iters += 1
            if recovery_iters >= MAX_FAILED_TOOL_RECOVERY_ITERS:
                yield ExecutionEvent(
                    EventType.TEXT_DELTA,
                    {"text": budget_exhausted_message(TOOL_FAILURE_BUDGET_MESSAGE)},
                )
                return

        if round_had_preflight:
            continue

    yield ExecutionEvent(
        EventType.TEXT_DELTA,
        {"text": budget_exhausted_message(TOOL_CALL_BUDGET_MESSAGE)},
    )

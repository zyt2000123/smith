"""Canonical ReAct loop shared by text, stream, and skill execution paths."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, AsyncGenerator

from engine.llm.client import ChatResponse, ToolCallData
from engine.llm.events import ProviderEvent, ProviderEventType
from engine.react_budget import (
    CONTINUE_AFTER_LENGTH_HINT,
    DEFAULT_MAX_REACT_ITERS,
    INCOMPLETE_FINAL_AFTER_TOOL_HINT,
    MAX_FAILED_TOOL_RECOVERY_ITERS,
    MAX_INCOMPLETE_FINAL_REPAIRS,
    MAX_LENGTH_CONTINUATIONS,
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


class IncompleteAgentRunError(RuntimeError):
    """Raised by text adapters when the canonical event stream ends incomplete."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Agent run ended incomplete: {reason}")


class FailedAgentRunError(RuntimeError):
    """Raised by text adapters when the canonical event stream ends with a hard failure."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Agent run failed: {reason}")


@dataclass
class _StreamedToolCall:
    id: str | None = None
    name: str | None = None
    argument_parts: list[str] = field(default_factory=list)


@dataclass
class _ProviderResponseAccumulator:
    """Reassemble one typed provider stream into the existing ChatResponse."""

    text_parts: list[str] = field(default_factory=list)
    reasoning_parts: list[str] = field(default_factory=list)
    tool_calls: dict[int, _StreamedToolCall] = field(default_factory=dict)
    usage: dict | None = None
    finish_reason: str | None = None
    raw_finish_reason: str | None = None
    streamed_text: bool = False

    def add(self, event: ProviderEvent) -> None:
        if event.type == ProviderEventType.OUTPUT_TEXT_DELTA:
            delta = event.data.get("delta")
            if isinstance(delta, str) and delta:
                self.text_parts.append(delta)
                self.streamed_text = True
            return

        if event.type == ProviderEventType.REASONING_DELTA:
            delta = event.data.get("delta")
            if isinstance(delta, str) and delta:
                self.reasoning_parts.append(delta)
            return

        if event.type == ProviderEventType.FUNCTION_CALL_ARGUMENTS_DELTA:
            index = event.data.get("index")
            if not isinstance(index, int):
                index = 0
            call = self.tool_calls.setdefault(index, _StreamedToolCall())
            call_id = event.data.get("id")
            if isinstance(call_id, str) and call_id:
                call.id = call_id
            name = event.data.get("name")
            if isinstance(name, str) and name:
                call.name = name
            arguments_delta = event.data.get("arguments_delta")
            if isinstance(arguments_delta, str):
                call.argument_parts.append(arguments_delta)
            return

        if event.type == ProviderEventType.USAGE:
            usage = event.data.get("usage")
            if isinstance(usage, dict):
                self.usage = usage
            return

        if event.type == ProviderEventType.RESPONSE_COMPLETED:
            finish_reason = event.data.get("finish_reason")
            raw_finish_reason = event.data.get("raw_finish_reason")
            self.finish_reason = finish_reason if isinstance(finish_reason, str) else None
            self.raw_finish_reason = raw_finish_reason if isinstance(raw_finish_reason, str) else None

    def build(self) -> ChatResponse:
        tool_calls: list[ToolCallData] = []
        for index in sorted(self.tool_calls):
            streamed_call = self.tool_calls[index]
            if self.finish_reason == "length":
                # The caller will turn this into an explicit incomplete run and
                # will not execute the placeholder.  Keeping a marker here is
                # safer than failing while parsing a known-truncated call and
                # accidentally collapsing it into a generic transport error.
                tool_calls.append(ToolCallData(
                    id=streamed_call.id or f"partial-call-{index}",
                    name=streamed_call.name or "__incomplete_tool_call__",
                    arguments={},
                ))
                continue
            if not streamed_call.id or not streamed_call.name:
                raise RuntimeError("Provider stream ended with incomplete tool-call metadata.")
            arguments_json = "".join(streamed_call.argument_parts) or "{}"
            try:
                arguments = json.loads(arguments_json)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Provider stream ended with invalid tool-call arguments.") from exc
            if not isinstance(arguments, dict):
                raise RuntimeError("Provider stream returned non-object tool-call arguments.")
            tool_calls.append(ToolCallData(
                id=streamed_call.id,
                name=streamed_call.name,
                arguments=arguments,
            ))

        return ChatResponse(
            text="".join(self.text_parts),
            reasoning="".join(self.reasoning_parts),
            tool_calls=tool_calls,
            usage=self.usage,
            finish_reason=self.finish_reason,
            raw_finish_reason=self.raw_finish_reason,
        )


def _raw_response_event(event: ProviderEvent) -> ExecutionEvent:
    return ExecutionEvent(
        EventType.RAW_RESPONSE_EVENT,
        {"type": event.type.value, "data": event.data},
    )


def _text_event(text: str, *, already_streamed: bool = False) -> ExecutionEvent:
    data: dict[str, object] = {"text": text}
    if already_streamed:
        data["already_streamed"] = True
    return ExecutionEvent(EventType.TEXT_DELTA, data)


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


def _append_length_continuation(conversation: list[dict], text: str) -> None:
    conversation.append({"role": "assistant", "content": text})
    conversation.append({"role": "system", "content": CONTINUE_AFTER_LENGTH_HINT})


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
        elif event.type == EventType.INCOMPLETE:
            raise IncompleteAgentRunError(
                str(event.data.get("reason", "agent_incomplete"))
            )
        elif event.type == EventType.FAILED:
            raise FailedAgentRunError(
                str(event.data.get("reason", "agent_failed"))
            )
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
        if event.type == EventType.RAW_RESPONSE_EVENT:
            raw_type = event.data.get("type")
            raw_data = event.data.get("data")
            if raw_type == ProviderEventType.OUTPUT_TEXT_DELTA.value and isinstance(raw_data, dict):
                text = raw_data.get("delta")
                if isinstance(text, str) and text:
                    yield text
        elif event.type == EventType.TEXT_DELTA:
            text = event.data.get("text", "")
            if text and not event.data.get("already_streamed"):
                yield str(text)
        elif event.type == EventType.INCOMPLETE:
            raise IncompleteAgentRunError(
                str(event.data.get("reason", "agent_incomplete"))
            )
        elif event.type == EventType.FAILED:
            raise FailedAgentRunError(
                str(event.data.get("reason", "agent_failed"))
            )


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
    length_continuations = 0
    final_text_parts: list[str] = []
    final_text_was_streamed = False

    while productive_iters < max_iters:
        conversation = await compress(conversation, llm)
        if len(conversation) > 40:
            conversation = [conversation[0]] + conversation[-30:]

        yield ExecutionEvent(EventType.THINKING, {})
        response_text_was_streamed = False
        stream_events = getattr(llm, "chat_events", None)
        if getattr(llm, "stream", False) and callable(stream_events):
            accumulator = _ProviderResponseAccumulator()
            saw_content_event = False
            try:
                async for provider_event in stream_events(conversation, tools=tools):
                    accumulator.add(provider_event)
                    yield _raw_response_event(provider_event)
                    # ponytail: only block fallback after user-visible content
                    if not saw_content_event and provider_event.type in (
                        ProviderEventType.OUTPUT_TEXT_DELTA,
                        ProviderEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
                    ):
                        saw_content_event = True
            except Exception:
                # Fallback to non-streaming only if no text/tool content was
                # emitted.  Metadata events (response.created, usage) are safe
                # to discard; text or tool-call fragments are not.
                if saw_content_event:
                    raise
                response = await llm.chat(conversation, tools=tools)
            else:
                response = accumulator.build()
                response_text_was_streamed = accumulator.streamed_text
        else:
            response = await llm.chat(conversation, tools=tools)
        usage = _usage_event_data(response.usage)
        if usage:
            yield ExecutionEvent(EventType.TOKEN_USAGE, usage)

        thought = (response.reasoning or (response.text if response.has_tool_calls else "")).strip()
        if thought:
            yield ExecutionEvent(EventType.THINKING, {"text": thought, "done": True})

        if response.finish_reason == "length" and response.has_tool_calls:
            # A length-limited tool call may have incomplete JSON arguments.
            # Never execute it or append a generic continuation prompt that
            # could change the requested action.
            if response.text:
                yield _text_event(
                    response.text,
                    already_streamed=response_text_was_streamed,
                )
            yield ExecutionEvent(EventType.INCOMPLETE, {
                "reason": "model_output_limit",
                "phase": "tool_call",
                "continuations": length_continuations,
            })
            return

        if response.has_tool_calls and response.finish_reason in {"content_filter", "other", "error"}:
            if response.text:
                yield _text_event(
                    response.text,
                    already_streamed=response_text_was_streamed,
                )
            if response.finish_reason == "error":
                yield ExecutionEvent(EventType.FAILED, {"reason": "provider_finish_error"})
            else:
                yield ExecutionEvent(EventType.INCOMPLETE, {
                    "reason": (
                        "content_filter"
                        if response.finish_reason == "content_filter"
                        else "unknown_provider_finish_reason"
                    ),
                    "raw_finish_reason": response.raw_finish_reason,
                })
            return

        if not response.has_tool_calls:
            if response.text:
                final_text_parts.append(response.text)
                final_text_was_streamed = final_text_was_streamed or response_text_was_streamed
            final_text = "".join(final_text_parts)

            if response.finish_reason == "length":
                if length_continuations < MAX_LENGTH_CONTINUATIONS:
                    length_continuations += 1
                    _append_length_continuation(conversation, response.text)
                    continue
                if final_text:
                    yield _text_event(final_text, already_streamed=final_text_was_streamed)
                yield ExecutionEvent(EventType.INCOMPLETE, {
                    "reason": "model_output_limit",
                    "continuations": length_continuations,
                })
                return

            if response.finish_reason == "content_filter":
                if final_text:
                    yield _text_event(final_text, already_streamed=final_text_was_streamed)
                yield ExecutionEvent(EventType.INCOMPLETE, {"reason": "content_filter"})
                return

            if response.finish_reason == "error":
                yield ExecutionEvent(EventType.FAILED, {"reason": "provider_finish_error"})
                return

            if response.finish_reason == "other":
                if final_text:
                    yield _text_event(final_text, already_streamed=final_text_was_streamed)
                yield ExecutionEvent(EventType.INCOMPLETE, {
                    "reason": "unknown_provider_finish_reason",
                    "raw_finish_reason": response.raw_finish_reason,
                })
                return

            if _should_repair_incomplete_final(
                final_text,
                had_successful_tool=had_successful_tool,
                repair_count=incomplete_final_repairs,
            ):
                incomplete_final_repairs += 1
                _append_incomplete_final_repair(conversation, final_text)
                final_text_parts.clear()
                final_text_was_streamed = False
                continue
            if final_text:
                yield _text_event(final_text, already_streamed=final_text_was_streamed)
            elif not had_successful_tool:
                yield ExecutionEvent(EventType.INCOMPLETE, {"reason": "empty_model_response"})
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
                yield ExecutionEvent(EventType.INCOMPLETE, {"reason": "preflight_budget"})
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
                yield ExecutionEvent(EventType.INCOMPLETE, {"reason": "tool_failure_budget"})
                return

        if round_had_preflight:
            continue

    yield ExecutionEvent(
        EventType.TEXT_DELTA,
        {"text": budget_exhausted_message(TOOL_CALL_BUDGET_MESSAGE)},
    )
    yield ExecutionEvent(EventType.INCOMPLETE, {"reason": "tool_call_budget"})

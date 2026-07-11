"""Provider-neutral events emitted while one model response is streamed.

The names intentionally mirror the useful parts of the OpenAI Responses
streaming vocabulary.  They are an engine-internal contract, not an HTTP/SSE
wire format: provider adapters translate their native chunks here and the
execution layer decides which events become user-visible progress.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProviderEventType(str, Enum):
    """Normalized low-level events from one provider response."""

    RESPONSE_CREATED = "response.created"
    OUTPUT_TEXT_DELTA = "response.output_text.delta"
    REASONING_DELTA = "response.reasoning.delta"
    FUNCTION_CALL_ARGUMENTS_DELTA = "response.function_call_arguments.delta"
    USAGE = "response.usage"
    RESPONSE_COMPLETED = "response.completed"


@dataclass(frozen=True)
class ProviderEvent:
    """One normalized provider stream event.

    ``data`` is deliberately limited to the information needed by the engine;
    raw provider payloads stay inside the provider adapter and are not exposed
    to frontends accidentally.
    """

    type: ProviderEventType
    data: dict[str, Any] = field(default_factory=dict)


def normalize_finish_reason(value: object) -> str | None:
    """Normalize common OpenAI-compatible finish reasons without losing raw data."""

    if not isinstance(value, str):
        return None

    raw = value.strip().lower()
    if not raw:
        return None

    aliases = {
        "stop": "stop",
        "end_turn": "stop",
        "stop_sequence": "stop",
        "length": "length",
        "max_tokens": "length",
        "tool_calls": "tool_calls",
        "function_call": "tool_calls",
        "tool_use": "tool_calls",
        "content_filter": "content_filter",
        "content-filter": "content_filter",
        "refusal": "content_filter",
        "error": "error",
    }
    return aliases.get(raw, "other")

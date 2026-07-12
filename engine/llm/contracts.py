"""Provider-neutral contracts owned by the :mod:`engine.llm` module.

Execution code intentionally talks only in terms of these values.  Provider
adapters are responsible for translating their wire formats into them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class LLMError(RuntimeError):
    """Base error raised by the normalized LLM module."""


class LLMResponseError(LLMError):
    """Raised when a provider returns a payload outside the internal contract."""


class UnsupportedProviderError(LLMError):
    """Raised when configuration names an adapter that is not registered."""


@dataclass(frozen=True)
class LLMTimeouts:
    """Phase-specific timeouts for one selected LLM execution route."""

    connect: float = 10.0
    read: float = 90.0
    stream_read: float = 120.0
    write: float = 30.0
    pool: float = 10.0

    def request_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect,
            read=self.read,
            write=self.write,
            pool=self.pool,
        )

    def stream_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect,
            read=self.stream_read,
            write=self.write,
            pool=self.pool,
        )


@dataclass(frozen=True)
class LLMRequest:
    """One provider-independent model request.

    ``messages`` and ``tools`` use the engine's existing conversation and tool
    representations.  Adapters translate them at their private seam.
    """

    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None
    prefix_cache_key: str | None = None


@dataclass(frozen=True)
class LLMProviderConfig:
    """Resolved connection configuration passed to an adapter factory."""

    provider: str
    api_key: str = field(repr=False)
    base_url: str
    model: str
    stream: bool = True
    timeouts: LLMTimeouts = field(default_factory=LLMTimeouts)
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class ProviderCapabilities:
    """Features an adapter can faithfully normalize for the execution layer."""

    streaming: bool = True
    tool_calls: bool = True
    reasoning: bool = False
    prefix_cache_key: bool = False


@dataclass
class ToolCallData:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResponse:
    """The complete normalized result of one model turn."""

    text: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCallData] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    raw_finish_reason: str | None = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

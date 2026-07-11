"""Internal Adapter Interface for provider-specific implementations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from ..contracts import ChatResponse, LLMRequest, ProviderCapabilities
from ..events import ProviderEvent


@runtime_checkable
class ProviderAdapter(Protocol):
    """Satisfies the private Adapter seam behind :class:`engine.llm.LLMPort`."""

    provider: str
    capabilities: ProviderCapabilities

    async def complete(self, request: LLMRequest) -> ChatResponse: ...

    def stream_response(self, request: LLMRequest) -> AsyncIterator[ProviderEvent]: ...

    async def close(self) -> None: ...

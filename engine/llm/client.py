"""Provider-neutral client facade over one concrete adapter.

New engine code should depend on :class:`engine.llm.port.LLMPort` and build
instances through :func:`engine.llm.factory.create_llm_client`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .adapters.base import ProviderAdapter
from .contracts import ChatResponse, LLMRequest, ToolCallData
from .events import ProviderEvent, ProviderEventType


class ProviderClient:
    """Facade that exposes the normalized Interface over one Adapter."""

    def __init__(self, adapter: ProviderAdapter, *, stream: bool = True) -> None:
        self._adapter = adapter
        self.stream = stream
        self.provider = adapter.provider
        self.capabilities = adapter.capabilities
        self.context_window = adapter.context_window
        self.context_window_declared = adapter.context_window_declared

    @property
    def adapter(self) -> ProviderAdapter:
        """Expose the concrete Adapter only for module-level construction/tests."""
        return self._adapter

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        prefix_cache_key: str | None = None,
    ) -> ChatResponse:
        return await self._adapter.complete(
            LLMRequest(
                messages=messages,
                tools=tools,
                prefix_cache_key=prefix_cache_key,
            )
        )

    def chat_events(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        return self._adapter.stream_response(LLMRequest(messages=messages, tools=tools))

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[str]:
        """Legacy text-only stream — yields only text deltas, no tool calls."""
        async for event in self.chat_events(messages):
            if event.type != ProviderEventType.OUTPUT_TEXT_DELTA:
                continue
            text = event.data.get("delta")
            if isinstance(text, str) and text:
                yield text

    async def close(self) -> None:
        await self._adapter.close()


__all__ = (
    "ChatResponse",
    "ProviderClient",
    "ToolCallData",
)

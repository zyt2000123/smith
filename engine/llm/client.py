"""Provider-neutral client facade over one concrete adapter.

New engine code should depend on :class:`engine.llm.port.LLMPort` and build
instances through :func:`engine.llm.factory.create_llm_client`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from .adapters.base import ProviderAdapter
from .contracts import ChatResponse, LLMRequest, LLMResponseError, ToolCallData
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
        self._validate_requested_capabilities(tools, prefix_cache_key)
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
        self._validate_requested_capabilities(tools, None)
        if not self.stream:
            return self._complete_as_events(messages, tools)
        if not self.capabilities.streaming:
            raise LLMResponseError(f"Provider {self.provider} does not support streaming.")
        return self._adapter.stream_response(LLMRequest(messages=messages, tools=tools))

    def _validate_requested_capabilities(
        self,
        tools: list[dict[str, Any]] | None,
        prefix_cache_key: str | None,
    ) -> None:
        if tools and not self.capabilities.tool_calls:
            raise LLMResponseError(f"Provider {self.provider} does not support tool calls.")
        if prefix_cache_key and not self.capabilities.prefix_cache_key:
            raise LLMResponseError(f"Provider {self.provider} does not support a prefix cache key.")

    async def _complete_as_events(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> AsyncIterator[ProviderEvent]:
        """Normalize a non-streaming completion into the same event contract."""
        yield ProviderEvent(ProviderEventType.RESPONSE_CREATED, {"provider": self.provider})
        response = await self.chat(messages, tools)
        if response.reasoning:
            yield ProviderEvent(ProviderEventType.REASONING_DELTA, {"delta": response.reasoning})
        if response.text:
            yield ProviderEvent(ProviderEventType.OUTPUT_TEXT_DELTA, {"delta": response.text})
        for index, tool_call in enumerate(response.tool_calls):
            yield ProviderEvent(
                ProviderEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
                {
                    "index": index,
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "arguments_delta": json.dumps(tool_call.arguments, separators=(",", ":")),
                },
            )
        if response.usage is not None:
            yield ProviderEvent(ProviderEventType.USAGE, {"usage": response.usage})
        yield ProviderEvent(
            ProviderEventType.RESPONSE_COMPLETED,
            {
                "finish_reason": response.finish_reason,
                "raw_finish_reason": response.raw_finish_reason,
            },
        )

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

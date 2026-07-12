"""Provider-neutral client facade and compatibility entry point.

New engine code should depend on :class:`engine.llm.port.LLMPort`.  The
``LLMClient`` class remains as a compatibility constructor for callers that
previously instantiated the OpenAI implementation directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .adapters.base import ProviderAdapter
from .adapters.openai import OpenAIAdapter
from .contracts import (
    ChatResponse,
    LLMProviderConfig,
    LLMRequest,
    LLMResponseError,
    LLMTimeouts,
    ProviderCapabilities,
    ToolCallData,
)
from .events import ProviderEvent, ProviderEventType


class ProviderClient:
    """Facade that exposes the normalized Interface over one Adapter."""

    def __init__(self, adapter: ProviderAdapter, *, stream: bool = True) -> None:
        self._adapter = adapter
        self.stream = stream
        self.provider = adapter.provider
        self.capabilities: ProviderCapabilities = adapter.capabilities

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


class LLMClient(ProviderClient):
    """Backward-compatible OpenAI constructor.

    This class deliberately contains no provider protocol logic. It delegates
    all implementation to :class:`OpenAIAdapter`, preserving old call sites
    while the rest of the engine migrates to ``LLMPort``.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        stream: bool = True,
        timeouts: LLMTimeouts | None = None,
    ) -> None:
        self._openai_adapter = OpenAIAdapter(
            LLMProviderConfig(
                provider="openai",
                api_key=api_key,
                base_url=base_url,
                model=model,
                stream=stream,
                timeouts=timeouts or LLMTimeouts(),
            )
        )
        super().__init__(self._openai_adapter, stream=stream)

    @property
    def api_key(self) -> str:
        return self._openai_adapter.api_key

    @property
    def base_url(self) -> str:
        return self._openai_adapter.base_url

    @property
    def model(self) -> str:
        return self._openai_adapter.model

    @property
    def timeouts(self) -> LLMTimeouts:
        return self._openai_adapter.timeouts

    @property
    def _http(self):  # compatibility for existing direct transport tests
        return self._openai_adapter._http

    async def _request(self, body: dict[str, Any], _attempt: int = 0) -> dict[str, Any]:
        return await self._openai_adapter._request(body, _attempt)

    _first_message_choice = staticmethod(OpenAIAdapter._first_message_choice)
    _parse_tool_call = staticmethod(OpenAIAdapter._parse_tool_call)

    async def _wait_for_retry(self, attempt: int, retry_after: float | None = None) -> None:
        await self._openai_adapter._wait_for_retry(attempt, retry_after)

    async def _retry_with_backoff(
        self,
        body: dict[str, Any],
        attempt: int,
        *,
        retry_after: float | None = None,
    ) -> dict[str, Any]:
        return await self._openai_adapter._retry_with_backoff(
            body,
            attempt,
            retry_after=retry_after,
        )


__all__ = (
    "ChatResponse",
    "LLMClient",
    "LLMResponseError",
    "LLMTimeouts",
    "ProviderClient",
    "ToolCallData",
)

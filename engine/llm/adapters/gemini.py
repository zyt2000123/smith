"""Adapter for Gemini's OpenAI-compatible Chat Completions endpoint."""

from __future__ import annotations

from dataclasses import replace

from ..contracts import (
    GEMINI_OPENAI_BASE_URL,
    LLMProviderConfig,
    LLMRequest,
    ProviderCapabilities,
)
from .openai import OpenAIAdapter


class GeminiAdapter(OpenAIAdapter):
    """Translate Gemini OpenAI-compatible payloads into internal contracts."""

    provider = "gemini"
    capabilities = ProviderCapabilities(
        streaming=True,
        tool_calls=True,
        reasoning=True,
        prefix_cache_key=False,
    )

    def __init__(self, config: LLMProviderConfig) -> None:
        base_url = config.base_url.strip() or GEMINI_OPENAI_BASE_URL
        super().__init__(replace(config, provider=self.provider, base_url=base_url))

    def _request_body(self, request: LLMRequest, *, stream: bool) -> dict:
        # Gemini exposes OpenAI-compatible chat completions, but prefix cache
        # hints are not part of the shared compatibility surface.
        return super()._request_body(
            LLMRequest(
                messages=request.messages,
                tools=request.tools,
                prefix_cache_key=None,
            ),
            stream=stream,
        )

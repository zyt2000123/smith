"""Provider-neutral LLM module public surface."""

from .client import ProviderClient
from .contracts import (
    ChatResponse,
    LLMError,
    LLMProviderConfig,
    LLMRequest,
    LLMResponseError,
    LLMTimeouts,
    ProviderCapabilities,
    ToolCallData,
    UnsupportedProviderError,
)
from .events import ProviderEvent, ProviderEventType
from .factory import create_llm_client, normalize_provider_name, supported_provider_names
from .port import LLMPort

__all__ = (
    "ChatResponse",
    "LLMError",
    "LLMPort",
    "LLMProviderConfig",
    "LLMRequest",
    "LLMResponseError",
    "LLMTimeouts",
    "ProviderCapabilities",
    "ProviderClient",
    "ProviderEvent",
    "ProviderEventType",
    "ToolCallData",
    "UnsupportedProviderError",
    "create_llm_client",
    "normalize_provider_name",
    "supported_provider_names",
)

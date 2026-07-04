from __future__ import annotations

from dataclasses import dataclass

from .client import LLMClient


@dataclass
class ModelConfig:
    api_key: str
    base_url: str
    model: str
    provider: str = ""
    stream: bool = True


def build_llm_client(config: dict) -> LLMClient:
    """Build an LLMClient from a merged config dict (from config_loader)."""
    return LLMClient(
        api_key=config["api_key"],
        base_url=config["base_url"],
        model=config["model"],
        stream=config.get("stream", True),
    )

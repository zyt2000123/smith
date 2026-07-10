from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from common.config import DATA_DIR, LEGACY_AGENT_PROFILES_DIR, SMITH_PROFILE_DIR
from common.yaml_utils import load_yaml, merge_configs

from .client import LLMClient

SMITH_TEMPLATE_ID = "personal-assistant"


@dataclass
class ModelConfig:
    api_key: str
    base_url: str
    model: str
    provider: str = ""
    stream: bool = True


def build_llm_client(config: dict) -> LLMClient:
    """Build an LLMClient from a merged config dict."""
    return LLMClient(
        api_key=config["api_key"],
        base_url=config["base_url"],
        model=config["model"],
        stream=config.get("stream", True),
    )


def resolve_llm_config(
    agent_id: str,
    template_id: str | None = None,
    session_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge four config levels and return LLM config.

    Levels (lower overrides upper):
      1. Platform:  ~/.agent-smith/config.yaml
      2. Smith:     agents/smith/config.yaml
      3. Profile:   legacy LEGACY_AGENT_PROFILES_DIR/<id>/config.yaml
      4. Session:   dict passed at runtime
    """
    env_defaults: dict[str, Any] = {}
    env_llm: dict[str, str] = {}
    for env_key, cfg_key in (
        ("AGENTSMITH_LLM_API_KEY", "api_key"),
        ("AGENTSMITH_LLM_BASE_URL", "base_url"),
        ("AGENTSMITH_LLM_MODEL", "model"),
        ("AGENTSMITH_LLM_PROVIDER", "provider"),
    ):
        val = os.environ.get(env_key)
        if val:
            env_llm[cfg_key] = val
    if env_llm:
        env_defaults["llm"] = env_llm

    platform = load_yaml(DATA_DIR / "config.yaml")

    template: dict[str, Any] = {}
    if template_id is None or template_id == SMITH_TEMPLATE_ID:
        template = load_yaml(SMITH_PROFILE_DIR / "config.yaml")

    agent = load_yaml(LEGACY_AGENT_PROFILES_DIR / agent_id / "config.yaml")

    merged = merge_configs(env_defaults, platform, template, agent, session_override or {})

    llm = merged.get("llm", merged)
    return {
        "api_key": llm.get("api_key", ""),
        "base_url": llm.get("base_url", ""),
        "model": llm.get("model", ""),
        "provider": llm.get("provider", ""),
        "stream": llm.get("stream", True),
    }

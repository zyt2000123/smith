from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import DATA_DIR, TEMPLATES_DIR
from .yaml_utils import load_yaml


def merge_configs(*configs: dict[str, Any]) -> dict[str, Any]:
    """Deep merge dicts. Later overrides earlier."""
    result: dict[str, Any] = {}
    for cfg in configs:
        for key, value in cfg.items():
            if value is None:
                continue
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = merge_configs(result[key], value)
            else:
                result[key] = value
    return result


def resolve_llm_config(
    employee_id: str,
    template_id: str | None = None,
    session_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge four config levels and return LLM config.

    Levels (lower overrides upper):
      1. Platform:  ~/.agent-smith/config.yaml
      2. Template:  agents/templates/<role>/config.yaml
      3. Employee:  ~/.agent-smith/employees/<id>/config.yaml
      4. Session:   dict passed at runtime
    """
    # Lowest priority: environment variables
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
    if template_id:
        template = load_yaml(TEMPLATES_DIR / template_id / "config.yaml")

    employee = load_yaml(DATA_DIR / "employees" / employee_id / "config.yaml")

    merged = merge_configs(env_defaults, platform, template, employee, session_override or {})

    llm = merged.get("llm", merged)
    return {
        "api_key": llm.get("api_key", ""),
        "base_url": llm.get("base_url", ""),
        "model": llm.get("model", ""),
        "provider": llm.get("provider", ""),
        "stream": llm.get("stream", True),
    }

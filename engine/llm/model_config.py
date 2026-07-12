from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from common.config import AGENT_DIR, DATA_DIR, SMITH_PROFILE_DIR
from common.yaml_utils import YamlConfigError, load_yaml, merge_configs

from .contracts import (
    GEMINI_OPENAI_BASE_URL,
    LLMProviderConfig,
    LLMTimeouts,
    UnsupportedProviderError,
)
from .factory import create_llm_client, normalize_provider_name
from .port import LLMPort

SMITH_TEMPLATE_ID = "personal-assistant"


class LLMUsage(str, Enum):
    """Caller intent used to select an LLM route and timeout profile."""

    INTERACTIVE = "interactive"
    GATE = "gate"
    BACKGROUND = "background"


_TIMEOUT_FIELDS = frozenset({"connect", "read", "stream_read", "write", "pool"})
_TIMEOUT_DEFAULTS: dict[LLMUsage, dict[str, float]] = {
    LLMUsage.INTERACTIVE: {
        "connect": 10.0,
        "read": 90.0,
        "stream_read": 120.0,
        "write": 30.0,
        "pool": 10.0,
    },
    LLMUsage.GATE: {
        "connect": 10.0,
        "read": 90.0,
        "stream_read": 90.0,
        "write": 30.0,
        "pool": 10.0,
    },
    LLMUsage.BACKGROUND: {
        "connect": 10.0,
        "read": 240.0,
        "stream_read": 300.0,
        "write": 30.0,
        "pool": 10.0,
    },
}
_ROUTE_FIELDS = (
    "api_key",
    "base_url",
    "model",
    "provider",
    "stream",
    "max_output_tokens",
)


@dataclass
class ModelConfig:
    api_key: str = field(repr=False)
    base_url: str
    model: str
    provider: str = ""
    stream: bool = True
    max_output_tokens: int | None = None


def build_llm_client(config: dict) -> LLMPort:
    """Build the normalized LLM Interface from a merged configuration dict.

    Resolution deliberately tolerates an empty configuration so optional
    background jobs can elect not to run.  Construction is the boundary where
    a caller has committed to making a provider request, so reject incomplete
    credentials here with a configuration error rather than failing later in
    httpx with an opaque URL or authentication error.
    """
    if not isinstance(config, dict):
        raise YamlConfigError("LLM configuration must be a mapping")

    provider_value = config.get("provider", "")
    try:
        provider = normalize_provider_name(provider_value)
    except UnsupportedProviderError as exc:
        raise YamlConfigError(str(exc)) from exc

    base_url = config.get("base_url")
    if provider == "gemini" and (base_url is None or str(base_url).strip() == ""):
        base_url = GEMINI_OPENAI_BASE_URL

    required_values = {
        "api_key": config.get("api_key"),
        "base_url": base_url,
        "model": config.get("model"),
    }
    missing = [
        field
        for field, value in required_values.items()
        if not isinstance(value, str) or not value.strip()
    ]
    if missing:
        fields = ", ".join(missing)
        raise YamlConfigError(f"LLM configuration is missing required fields: {fields}")

    stream = config.get("stream", True)
    if not isinstance(stream, bool):
        raise YamlConfigError("LLM stream configuration must be a boolean")

    max_output_tokens = config.get("max_output_tokens")
    if max_output_tokens is not None and (
        isinstance(max_output_tokens, bool)
        or not isinstance(max_output_tokens, int)
        or max_output_tokens <= 0
    ):
        raise YamlConfigError("LLM max_output_tokens must be a positive integer")

    timeout = config.get("timeout")
    if timeout is None:
        timeouts = None
    elif isinstance(timeout, LLMTimeouts):
        timeouts = timeout
    elif isinstance(timeout, dict):
        unknown_timeout_fields = set(timeout) - _TIMEOUT_FIELDS
        if unknown_timeout_fields:
            names = ", ".join(sorted(unknown_timeout_fields))
            raise YamlConfigError(f"Unknown LLM timeout fields: {names}")
        try:
            timeouts = LLMTimeouts(**timeout)
        except TypeError as exc:
            raise YamlConfigError("Invalid LLM timeout configuration") from exc
    else:
        raise YamlConfigError("LLM timeout configuration must be a mapping")

    resolved_timeouts = timeouts or LLMTimeouts()
    for field in _TIMEOUT_FIELDS:
        value = getattr(resolved_timeouts, field)
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or value <= 0
        ):
            raise YamlConfigError(f"LLM timeout {field} must be a positive number")

    return create_llm_client(LLMProviderConfig(
        provider=provider,
        api_key=config["api_key"].strip(),
        base_url=base_url.strip(),
        model=config["model"].strip(),
        stream=stream,
        timeouts=resolved_timeouts,
        max_output_tokens=max_output_tokens,
    ))


def _as_usage(value: LLMUsage | str) -> LLMUsage:
    if isinstance(value, LLMUsage):
        return value
    try:
        return LLMUsage(value)
    except ValueError as exc:
        allowed = ", ".join(usage.value for usage in LLMUsage)
        raise YamlConfigError(f"Unknown LLM usage {value!r}; expected one of: {allowed}") from exc


def _mapping(value: object, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise YamlConfigError(f"{label} must be a mapping")
    return value


def _resolve_timeout(
    llm: dict[str, Any],
    usage: LLMUsage,
    route: dict[str, Any],
) -> dict[str, float]:
    profile_name = route.get("timeout_profile", usage.value)
    if not isinstance(profile_name, str):
        raise YamlConfigError("LLM timeout_profile must be a string")
    try:
        profile = LLMUsage(profile_name)
    except ValueError as exc:
        allowed = ", ".join(usage.value for usage in LLMUsage)
        raise YamlConfigError(
            f"Unknown LLM timeout profile {profile_name!r}; expected one of: {allowed}"
        ) from exc

    timeout_profiles = _mapping(llm.get("timeout_profiles"), "LLM timeout_profiles")
    override = _mapping(
        timeout_profiles.get(profile.value),
        f"LLM timeout profile {profile.value!r}",
    )
    unknown = set(override) - _TIMEOUT_FIELDS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise YamlConfigError(f"Unknown LLM timeout fields: {names}")

    resolved = dict(_TIMEOUT_DEFAULTS[profile])
    resolved.update(override)
    for name, value in resolved.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or value <= 0
        ):
            raise YamlConfigError(f"LLM timeout {profile.value}.{name} must be a positive number")
        resolved[name] = float(value)
    return resolved


def resolve_llm_config(
    session_override: dict[str, Any] | None = None,
    usage: LLMUsage | str = LLMUsage.INTERACTIVE,
) -> dict[str, Any]:
    """Return the selected LLM route after merging config levels.

    Levels (lower overrides upper):
      1. Environment defaults
      2. Platform:  ~/.agent-smith/config.yaml
      3. Smith seed: agents/smith/config.yaml
      4. Smith runtime: ~/.agent-smith/agent/config.yaml
      5. Session:   dict passed at runtime

    ``llm.routes`` may override the base config for ``interactive``, ``gate``,
    or ``background``.  Omitted routes inherit the base model unchanged.
    """
    selected_usage = _as_usage(usage)
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

    template = load_yaml(SMITH_PROFILE_DIR / "config.yaml")
    agent = load_yaml(AGENT_DIR / "config.yaml")

    merged = merge_configs(env_defaults, platform, template, agent, session_override or {})

    llm = merged.get("llm", merged)
    if not isinstance(llm, dict):
        raise YamlConfigError("LLM configuration must be a mapping")

    routes = _mapping(llm.get("routes"), "LLM routes")
    route = _mapping(routes.get(selected_usage.value), f"LLM route {selected_usage.value!r}")
    defaults: dict[str, Any] = {
        "provider": "",
        "stream": True,
        "max_output_tokens": None,
    }
    selected = {
        field: route[field] if field in route else llm.get(field, defaults.get(field, ""))
        for field in _ROUTE_FIELDS
    }
    selected["timeout"] = _resolve_timeout(llm, selected_usage, route)
    return selected

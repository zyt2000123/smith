from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.yaml_utils import YamlConfigError  # noqa: E402
from app.services import engine_runtime  # noqa: E402
from engine.llm import model_config  # noqa: E402


def test_resolve_llm_config_loads_builtin_smith_profile_by_default(
    tmp_path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "data"
    smith_dir = tmp_path / "smith"
    smith_dir.mkdir()
    (smith_dir / "config.yaml").write_text(
        "llm:\n  model: smith-default\n  provider: openai\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(model_config, "DATA_DIR", data_dir)
    monkeypatch.setattr(model_config, "LEGACY_AGENT_PROFILES_DIR", data_dir / "agent_profiles")
    monkeypatch.setattr(model_config, "SMITH_PROFILE_DIR", smith_dir)
    for env_key in (
        "AGENTSMITH_LLM_API_KEY",
        "AGENTSMITH_LLM_BASE_URL",
        "AGENTSMITH_LLM_MODEL",
        "AGENTSMITH_LLM_PROVIDER",
    ):
        monkeypatch.delenv(env_key, raising=False)

    cfg = model_config.resolve_llm_config("smith-id")
    gate_cfg = model_config.resolve_llm_config(
        "smith-id",
        usage=model_config.LLMUsage.GATE,
    )

    assert cfg["model"] == "smith-default"
    assert cfg["provider"] == "openai"
    assert gate_cfg["model"] == "smith-default"  # 未配置 route 时回退主模型
    assert gate_cfg["timeout"]["read"] == 90.0
    assert gate_cfg["timeout"]["stream_read"] == 90.0


def test_resolve_llm_config_selects_model_routes_and_timeout_profiles(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text(
        """
llm:
  api_key: primary-key
  base_url: https://primary.example/v1
  model: primary-model
  stream: true
  routes:
    gate:
      model: cheap-gate-model
    background:
      base_url: https://background.example/v1
      model: cheap-background-model
  timeout_profiles:
    gate:
      read: 45
    background:
      read: 250
      stream_read: 280
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(model_config, "DATA_DIR", data_dir)
    monkeypatch.setattr(model_config, "SMITH_PROFILE_DIR", tmp_path / "missing-smith")
    monkeypatch.setattr(model_config, "LEGACY_AGENT_PROFILES_DIR", tmp_path / "missing-profiles")

    interactive = model_config.resolve_llm_config(
        "smith-id",
        usage=model_config.LLMUsage.INTERACTIVE,
    )
    gate = model_config.resolve_llm_config("smith-id", usage=model_config.LLMUsage.GATE)
    background = model_config.resolve_llm_config(
        "smith-id",
        usage=model_config.LLMUsage.BACKGROUND,
    )

    assert interactive["model"] == "primary-model"
    assert interactive["timeout"]["read"] == 90.0
    assert interactive["timeout"]["stream_read"] == 120.0
    assert gate["api_key"] == "primary-key"
    assert gate["model"] == "cheap-gate-model"
    assert gate["timeout"]["read"] == 45.0
    assert gate["timeout"]["stream_read"] == 90.0
    assert background["base_url"] == "https://background.example/v1"
    assert background["model"] == "cheap-background-model"
    assert background["timeout"]["read"] == 250.0
    assert background["timeout"]["stream_read"] == 280.0


def test_resolve_llm_config_rejects_a_non_mapping_llm_config(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text("llm: invalid\n", encoding="utf-8")

    monkeypatch.setattr(model_config, "DATA_DIR", data_dir)
    monkeypatch.setattr(model_config, "SMITH_PROFILE_DIR", tmp_path / "missing-smith")
    monkeypatch.setattr(model_config, "LEGACY_AGENT_PROFILES_DIR", tmp_path / "missing-profiles")

    with pytest.raises(YamlConfigError, match="LLM configuration"):
        model_config.resolve_llm_config("smith-id")


@pytest.mark.parametrize("field", ["api_key", "base_url", "model"])
def test_build_llm_client_fails_fast_for_missing_required_config(field: str) -> None:
    config = {
        "api_key": "test-key",
        "base_url": "https://provider.example/v1",
        "model": "test-model",
    }
    config[field] = ""

    with pytest.raises(YamlConfigError, match=field):
        model_config.build_llm_client(config)


def test_resolve_llm_config_rejects_non_finite_timeout_values(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text(
        """
llm:
  api_key: test-key
  base_url: https://provider.example/v1
  model: test-model
  timeout_profiles:
    gate:
      read: .inf
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(model_config, "DATA_DIR", data_dir)
    monkeypatch.setattr(model_config, "SMITH_PROFILE_DIR", tmp_path / "missing-smith")
    monkeypatch.setattr(model_config, "LEGACY_AGENT_PROFILES_DIR", tmp_path / "missing-profiles")

    with pytest.raises(YamlConfigError, match="positive number"):
        model_config.resolve_llm_config("smith-id", usage=model_config.LLMUsage.GATE)


def test_route_can_select_native_anthropic_adapter_and_generation_limit(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text(
        """
llm:
  provider: openai
  api_key: openai-key
  base_url: https://openai.example/v1
  model: openai-model
  routes:
    gate:
      provider: anthropic
      api_key: anthropic-key
      base_url: https://api.anthropic.com
      model: claude-test
      max_output_tokens: 768
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(model_config, "DATA_DIR", data_dir)
    monkeypatch.setattr(model_config, "SMITH_PROFILE_DIR", tmp_path / "missing-smith")
    monkeypatch.setattr(model_config, "LEGACY_AGENT_PROFILES_DIR", tmp_path / "missing-profiles")

    gate = model_config.resolve_llm_config("smith-id", usage=model_config.LLMUsage.GATE)
    client = model_config.build_llm_client(gate)
    try:
        assert gate["provider"] == "anthropic"
        assert gate["max_output_tokens"] == 768
        assert client.provider == "anthropic"
        assert type(client.adapter).__name__ == "AnthropicAdapter"
    finally:
        import asyncio
        asyncio.run(client.close())


def test_build_engine_runtime_selects_interactive_and_gate_clients(monkeypatch) -> None:
    selected_usages: list[model_config.LLMUsage] = []
    clients: list[object] = []

    def fake_resolve(agent_id: str, *, usage: model_config.LLMUsage) -> dict:
        assert agent_id == "smith-id"
        selected_usages.append(usage)
        return {"usage": usage.value}

    def fake_build(config: dict) -> object:
        client = object()
        clients.append(client)
        return client

    monkeypatch.setattr(engine_runtime, "resolve_llm_config", fake_resolve)
    monkeypatch.setattr(engine_runtime, "build_llm_client", fake_build)
    monkeypatch.setattr(engine_runtime, "ToolRegistry", lambda: object())
    monkeypatch.setattr(engine_runtime, "SkillRegistry", lambda: object())
    monkeypatch.setattr(engine_runtime, "ToolGuard", lambda _path: object())

    runtime, services = engine_runtime.build_engine_runtime("smith-id", "Smith")

    assert runtime.agent_id == "smith-id"

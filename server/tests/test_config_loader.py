from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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

    assert cfg["model"] == "smith-default"
    assert cfg["provider"] == "openai"

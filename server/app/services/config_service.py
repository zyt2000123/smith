from __future__ import annotations

from common.config import DATA_DIR
from common.yaml_utils import load_yaml, save_yaml


class ConfigService:

    _config_path = DATA_DIR / "config.yaml"

    def get_llm_config(self) -> dict:
        cfg = load_yaml(self._config_path)
        llm = cfg.get("llm", {})
        return {
            "configured": bool(llm.get("api_key")),
            "has_api_key": bool(llm.get("api_key")),
            "provider": llm.get("provider") or "openai",
            "model": llm.get("model", ""),
            "base_url": llm.get("base_url", ""),
        }

    def set_llm_config(
        self,
        *,
        provider: str,
        api_key: str | None,
        base_url: str | None,
        model: str,
    ) -> dict:
        cfg = load_yaml(self._config_path)
        cfg.setdefault("llm", {})

        cfg["llm"]["provider"] = provider or cfg["llm"].get("provider") or "openai"
        if api_key is not None and api_key.strip():
            cfg["llm"]["api_key"] = api_key.strip()
        if base_url is not None:
            cfg["llm"]["base_url"] = base_url
        cfg["llm"]["model"] = model
        save_yaml(self._config_path, cfg)
        result = self.get_llm_config()
        result["status"] = "ok"
        return result

from __future__ import annotations

from common.config import SMITH_PROFILE_DIR
from engine.llm.model_config import SMITH_TEMPLATE_ID
from common.yaml_utils import load_yaml


ACTIVE_TEMPLATE_IDS = {SMITH_TEMPLATE_ID}


class TemplateService:

    async def list_templates(self) -> list[dict]:
        if not SMITH_PROFILE_DIR.is_dir():
            return []

        cfg = load_yaml(SMITH_PROFILE_DIR / "config.yaml")
        if not cfg:
            return []

        return [{
            "id": SMITH_TEMPLATE_ID,
            "title": cfg.get("name", SMITH_TEMPLATE_ID),
            "description": cfg.get("description", ""),
            "knowledge": cfg.get("knowledge", []),
        }]

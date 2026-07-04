from __future__ import annotations

from common.config import TEMPLATES_DIR
from common.yaml_utils import load_yaml


class TemplateService:

    async def list_templates(self) -> list[dict]:
        templates: list[dict] = []
        if not TEMPLATES_DIR.is_dir():
            return templates
        for d in sorted(TEMPLATES_DIR.iterdir()):
            if not d.is_dir():
                continue
            cfg = load_yaml(d / "config.yaml")
            if not cfg:
                continue
            templates.append({
                "id": d.name,
                "title": cfg.get("name", d.name),
                "description": cfg.get("description", ""),
                "knowledge": cfg.get("knowledge", []),
            })
        return templates

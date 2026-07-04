from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class SkillMeta:
    name: str
    description: str = ""
    version: str = "0.1.0"
    argument_hint: str = ""


@dataclass
class SkillBody:
    meta: SkillMeta
    content: str  # markdown body after frontmatter


def parse_skill_md(path: Path) -> SkillBody:
    """Parse a SKILL.md file with YAML frontmatter + markdown body."""
    raw = path.read_text(encoding="utf-8")

    meta_dict: dict = {}
    body = raw

    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            meta_dict = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()

    meta = SkillMeta(
        name=meta_dict.get("name", path.parent.name),
        description=meta_dict.get("description", ""),
        version=meta_dict.get("version", "0.1.0"),
        argument_hint=meta_dict.get("argument_hint", ""),
    )
    return SkillBody(meta=meta, content=body)

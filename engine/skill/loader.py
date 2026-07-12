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
            try:
                loaded = yaml.safe_load(parts[1])
            except yaml.YAMLError:
                loaded = None
            # Tolerate malformed frontmatter (invalid YAML or a non-mapping
            # root): strip the block but fall back to default metadata.
            meta_dict = loaded if isinstance(loaded, dict) else {}
            body = parts[2].strip()

    name = meta_dict.get("name")
    meta = SkillMeta(
        name=str(name) if name else path.parent.name,
        description=str(meta_dict.get("description") or ""),
        version=str(meta_dict.get("version") or "0.1.0"),
        argument_hint=str(meta_dict.get("argument_hint") or ""),
    )
    return SkillBody(meta=meta, content=body)

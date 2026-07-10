from __future__ import annotations

import shutil
from pathlib import Path

from common.config import LEGACY_AGENT_PROFILES_DIR


def agent_profile_dir(agent_id: str) -> Path:
    return LEGACY_AGENT_PROFILES_DIR / agent_id


def _safe_child(agent_id: str, filename: str) -> Path:
    base = agent_profile_dir(agent_id).resolve()
    p = (base / filename).resolve()
    if not p.is_relative_to(base):
        raise ValueError("path traversal")
    return p


def init_agent_profile_files(
    agent_id: str,
    *,
    profile_seed_dir: Path,
    name: str,
    role: str,
    description: str,
) -> None:
    dest = agent_profile_dir(agent_id)
    dest.mkdir(parents=True, exist_ok=True)

    if profile_seed_dir.is_dir():
        for item in profile_seed_dir.iterdir():
            target = dest / item.name
            if item.is_file():
                shutil.copy2(item, target)
            elif item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)

    for sub in ("memory", "sessions", "skills"):
        (dest / sub).mkdir(exist_ok=True)


def delete_agent_profile_files(agent_id: str) -> None:
    d = agent_profile_dir(agent_id)
    if d.exists():
        shutil.rmtree(d)


def read_agent_profile_file(agent_id: str, filename: str) -> str | None:
    p = _safe_child(agent_id, filename)
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return None


def write_agent_profile_file(agent_id: str, filename: str, content: str) -> None:
    p = _safe_child(agent_id, filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def list_agent_profile_files(agent_id: str) -> list[dict]:
    d = agent_profile_dir(agent_id)
    if not d.is_dir():
        return []
    return [
        {"filename": f.name, "size": f.stat().st_size}
        for f in d.iterdir()
        if f.is_file()
    ]

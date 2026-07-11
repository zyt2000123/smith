from __future__ import annotations

import shutil
from pathlib import Path

from common.config import AGENT_DIR


def smith_profile_dir() -> Path:
    """Return the one writable runtime profile owned by Smith."""
    return AGENT_DIR


def _safe_child(filename: str) -> Path:
    base = smith_profile_dir().resolve()
    p = (base / filename).resolve()
    if not p.is_relative_to(base):
        raise ValueError("path traversal")
    return p


def init_smith_profile_files(
    *,
    profile_seed_dir: Path,
    name: str,
    role: str,
    description: str,
) -> None:
    dest = smith_profile_dir()
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


def read_smith_profile_file(filename: str) -> str | None:
    p = _safe_child(filename)
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return None


def write_smith_profile_file(filename: str, content: str) -> None:
    p = _safe_child(filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def list_smith_profile_files() -> list[dict]:
    d = smith_profile_dir()
    if not d.is_dir():
        return []
    return [
        {"filename": f.name, "size": f.stat().st_size}
        for f in d.iterdir()
        if f.is_file()
    ]

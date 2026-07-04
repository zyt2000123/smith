from __future__ import annotations

import shutil
from pathlib import Path

from .config import EMPLOYEES_DIR


def employee_dir(employee_id: str) -> Path:
    return EMPLOYEES_DIR / employee_id


def init_employee_files(
    employee_id: str,
    *,
    template_dir: Path,
    name: str,
    role: str,
    description: str,
) -> None:
    dest = employee_dir(employee_id)
    dest.mkdir(parents=True, exist_ok=True)

    # Copy template files
    if template_dir.is_dir():
        for item in template_dir.iterdir():
            target = dest / item.name
            if item.is_file():
                shutil.copy2(item, target)
            elif item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)

    # Create standard subdirs
    for sub in ("memory", "sessions", "skills"):
        (dest / sub).mkdir(exist_ok=True)


def delete_employee_files(employee_id: str) -> None:
    d = employee_dir(employee_id)
    if d.exists():
        shutil.rmtree(d)


def read_employee_file(employee_id: str, filename: str) -> str | None:
    p = employee_dir(employee_id) / filename
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return None


def write_employee_file(employee_id: str, filename: str, content: str) -> None:
    p = employee_dir(employee_id) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def list_employee_files(employee_id: str) -> list[dict]:
    d = employee_dir(employee_id)
    if not d.is_dir():
        return []
    return [
        {"filename": f.name, "size": f.stat().st_size}
        for f in d.iterdir()
        if f.is_file()
    ]

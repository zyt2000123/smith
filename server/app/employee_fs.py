"""Employee file system operations — manages identity/persona/bible files under ~/.agent-smith/employees/<id>/"""
import yaml
from pathlib import Path
from .config import EMPLOYEES_DIR

def employee_dir(employee_id: str) -> Path:
    return EMPLOYEES_DIR / employee_id

def init_employee_files(employee_id: str, *, name: str, role: str, description: str,
                        identity: str = "", persona: str = "", knowledge: list[str] | None = None):
    d = employee_dir(employee_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "memory").mkdir(exist_ok=True)
    (d / "sessions").mkdir(exist_ok=True)

    config = {"name": name, "role": role, "description": description, "knowledge": knowledge or []}
    (d / "config.yaml").write_text(yaml.dump(config, allow_unicode=True, default_flow_style=False), encoding="utf-8")

    if not identity:
        identity = f"你是 {name}，一名{role}。\n\n{description}"
    (d / "identity.md").write_text(f"# {name}\n\n{identity}\n", encoding="utf-8")

    if not persona:
        persona = f"{name} 的工作风格。"
    (d / "persona.md").write_text(f"# 工作风格\n\n{persona}\n", encoding="utf-8")

    (d / "bible.md").write_text(f"# 工作流规范\n\n待定义。\n", encoding="utf-8")

def delete_employee_files(employee_id: str):
    import shutil
    d = employee_dir(employee_id)
    if d.exists():
        shutil.rmtree(d)

def read_employee_file(employee_id: str, filename: str) -> str | None:
    f = employee_dir(employee_id) / filename
    return f.read_text(encoding="utf-8") if f.exists() else None

def write_employee_file(employee_id: str, filename: str, content: str):
    f = employee_dir(employee_id) / filename
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")

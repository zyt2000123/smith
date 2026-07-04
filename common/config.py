from pathlib import Path

DATA_DIR = Path.home() / ".agent-smith"
EMPLOYEES_DIR = DATA_DIR / "employees"
SQLITE_PATH = DATA_DIR / "sqlite" / "agent-smith.sqlite"

_project_root = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = _project_root / "agents" / "templates"
BUILTIN_SKILLS_DIR = _project_root / "agents" / "skills"
BUILTIN_TOOLS_DIR = _project_root / "agents" / "tools"
SAFETY_RULES_PATH = _project_root / "agents" / "safety" / "dangerous_commands.json"
BUILTIN_PLUGINS_DIR = _project_root / "agents" / "plugins"
USER_PLUGINS_DIR = DATA_DIR / "plugins"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EMPLOYEES_DIR.mkdir(parents=True, exist_ok=True)
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)

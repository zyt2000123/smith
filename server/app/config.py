from pathlib import Path

DATA_DIR = Path.home() / ".agent-smith"
EMPLOYEES_DIR = DATA_DIR / "employees"
SQLITE_PATH = DATA_DIR / "sqlite" / "agent-smith.sqlite"

def ensure_dirs():
    for d in [EMPLOYEES_DIR, SQLITE_PATH.parent]:
        d.mkdir(parents=True, exist_ok=True)

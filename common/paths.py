from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

PROJECT_ROOT_ENV = "AGENT_SMITH_PROJECT_ROOT"
PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def _default_project_root() -> Path:
    configured_root = os.environ.get(PROJECT_ROOT_ENV)
    if configured_root:
        project_root = Path(configured_root).expanduser().resolve()
        if not (project_root / "agents").is_dir():
            raise RuntimeError(
                f"{PROJECT_ROOT_ENV} must point to an Agent-Smith root containing agents/"
            )
        return project_root

    source_root = Path(__file__).resolve().parent.parent
    if (source_root / "agents").is_dir():
        return source_root

    working_dir = Path.cwd().resolve()
    for candidate in (working_dir, *working_dir.parents):
        if (candidate / "agents").is_dir():
            return candidate

    return source_root


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIR_MODE)
    path.chmod(PRIVATE_DIR_MODE)


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    project_root: Path

    @classmethod
    def defaults(cls) -> "AppPaths":
        return cls(
            data_dir=Path.home() / ".agent-smith",
            project_root=_default_project_root(),
        )

    @property
    def agent_dir(self) -> Path:
        return self.data_dir / "agent"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "sqlite" / "agent-smith.sqlite"

    @property
    def smith_profile_dir(self) -> Path:
        return self.project_root / "agents" / "smith"

    @property
    def builtin_skills_dir(self) -> Path:
        return self.project_root / "agents" / "skills"

    @property
    def builtin_tools_dir(self) -> Path:
        return self.project_root / "agents" / "tools"

    @property
    def builtin_identities_dir(self) -> Path:
        return self.project_root / "agents" / "identities"

    @property
    def safety_rules_path(self) -> Path:
        return self.project_root / "agents" / "safety" / "dangerous_commands.json"

    def ensure_base_dirs(self) -> None:
        _ensure_private_dir(self.data_dir)
        _ensure_private_dir(self.agent_dir)
        _ensure_private_dir(self.sqlite_path.parent)

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    project_root: Path

    @classmethod
    def defaults(cls) -> "AppPaths":
        return cls(
            data_dir=Path.home() / ".agent-smith",
            project_root=Path(__file__).resolve().parent.parent,
        )

    @property
    def agent_dir(self) -> Path:
        return self.data_dir / "agent"

    @property
    def legacy_agent_profiles_dir(self) -> Path:
        return self.data_dir / "employees"

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
    def safety_rules_path(self) -> Path:
        return self.project_root / "agents" / "safety" / "dangerous_commands.json"

    @property
    def builtin_plugins_dir(self) -> Path:
        return self.project_root / "agents" / "plugins"

    @property
    def user_plugins_dir(self) -> Path:
        return self.data_dir / "plugins"

    def ensure_base_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        self.legacy_agent_profiles_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

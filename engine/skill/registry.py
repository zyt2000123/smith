from __future__ import annotations

from pathlib import Path

from .loader import SkillBody, parse_skill_md


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillBody] = {}
        self._builtin_names: set[str] = set()
        self._employee_skills_dir: Path | None = None

    def load_builtin(self, skills_dir: Path) -> None:
        """Scan *skills_dir* for subdirectories containing SKILL.md."""
        if not skills_dir.is_dir():
            return
        for child in sorted(skills_dir.iterdir()):
            skill_file = child / "SKILL.md"
            if skill_file.is_file():
                skill = parse_skill_md(skill_file)
                self._skills[skill.meta.name] = skill
                self._builtin_names.add(skill.meta.name)

    def load_employee_skills(self, employee_skills_dir: Path) -> None:
        """Load employee-specific skills (same layout as builtin)."""
        self._employee_skills_dir = employee_skills_dir
        if not employee_skills_dir.is_dir():
            return
        for child in sorted(employee_skills_dir.iterdir()):
            skill_file = child / "SKILL.md"
            if skill_file.is_file():
                skill = parse_skill_md(skill_file)
                self._skills[skill.meta.name] = skill

    def get(self, name: str) -> SkillBody | None:
        return self._skills.get(name)

    def is_builtin(self, name: str) -> bool:
        """Return True if the skill is a built-in (read-only) skill."""
        return name in self._builtin_names

    def get_employee_skill_dir(self, name: str) -> Path | None:
        """Return the path to an employee-installed skill's directory, or None."""
        if self._employee_skills_dir is None:
            return None
        if name in self._builtin_names:
            return None
        skill_dir = self._employee_skills_dir / name
        if skill_dir.is_dir():
            return skill_dir
        return None

    def list_summaries(self) -> list[dict]:
        return [
            {
                "name": s.meta.name,
                "description": s.meta.description,
                "source": "builtin" if s.meta.name in self._builtin_names else "employee",
            }
            for s in self._skills.values()
        ]

from __future__ import annotations

from pathlib import Path

from .loader import SkillBody, parse_skill_md


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillBody] = {}

    def load_builtin(self, skills_dir: Path) -> None:
        """Scan *skills_dir* for subdirectories containing SKILL.md."""
        if not skills_dir.is_dir():
            return
        for child in sorted(skills_dir.iterdir()):
            skill_file = child / "SKILL.md"
            if skill_file.is_file():
                skill = parse_skill_md(skill_file)
                self._skills[skill.meta.name] = skill

    def load_employee_skills(self, employee_skills_dir: Path) -> None:
        """Load employee-specific skills (same layout as builtin)."""
        self.load_builtin(employee_skills_dir)

    def get(self, name: str) -> SkillBody | None:
        return self._skills.get(name)

    def list_summaries(self) -> list[dict]:
        return [
            {"name": s.meta.name, "description": s.meta.description}
            for s in self._skills.values()
        ]

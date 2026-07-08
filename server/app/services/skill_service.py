from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from common.config import EMPLOYEES_DIR
from engine.skill.registry import SkillRegistry

from ..domain.skill import SkillSummaryOut
from ..infrastructure.repositories.employee_repo import EmployeeRepo


class SkillService:

    def __init__(self, employee_repo: EmployeeRepo) -> None:
        self.employee_repo = employee_repo

    async def list_skills(self, employee_id: str) -> list[SkillSummaryOut]:
        await self._ensure_employee(employee_id)
        registry = self._load_registry(employee_id)

        summaries: list[SkillSummaryOut] = []
        for item in sorted(registry.list_summaries(), key=lambda value: value["name"]):
            body = registry.get(item["name"])
            if body is None:
                continue
            summaries.append(
                SkillSummaryOut(
                    name=body.meta.name,
                    description=body.meta.description,
                    source=item["source"],
                    version=body.meta.version,
                    argument_hint=body.meta.argument_hint,
                )
            )
        return summaries

    async def ensure_skill_exists(self, employee_id: str, skill_name: str) -> SkillSummaryOut:
        await self._ensure_employee(employee_id)
        registry = self._load_registry(employee_id)
        body = registry.get(skill_name)
        if body is None:
            raise HTTPException(404, f"Skill '{skill_name}' not found")

        source = "builtin" if registry.is_builtin(skill_name) else "employee"
        return SkillSummaryOut(
            name=body.meta.name,
            description=body.meta.description,
            source=source,
            version=body.meta.version,
            argument_hint=body.meta.argument_hint,
        )

    async def _ensure_employee(self, employee_id: str) -> None:
        if await self.employee_repo.get(employee_id) is None:
            raise HTTPException(404, "Employee not found")

    @staticmethod
    def _load_registry(employee_id: str) -> SkillRegistry:
        registry = SkillRegistry()
        agents_dir = Path(__file__).resolve().parents[3] / "agents"
        registry.load_builtin(agents_dir / "skills")

        employee_skills_dir = EMPLOYEES_DIR / employee_id / "skills"
        if employee_skills_dir.is_dir():
            registry.load_employee_skills(employee_skills_dir)
        return registry

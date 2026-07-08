from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.skill_service import SkillService


class FakeEmployeeRepo:
    async def get(self, employee_id: str) -> dict | None:
        return {"id": employee_id, "name": "Smith"}


@pytest.mark.asyncio
async def test_list_skills_includes_builtin_metadata() -> None:
    svc = SkillService(FakeEmployeeRepo())

    skills = await svc.list_skills("emp-1")

    assert skills
    planning = next(skill for skill in skills if skill.name == "planning")
    assert planning.source == "builtin"
    assert planning.version == "1.0"
    assert "制定实现计划" in planning.description

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.skill_service import SkillService


class FakeAgentProfileRepo:
    async def get(self, agent_id: str) -> dict | None:
        return {"id": agent_id, "name": "Smith"}


@pytest.mark.asyncio
async def test_list_skills_allows_empty_builtin_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "app.services.skill_service.agent_profile_dir",
        lambda _agent_id: tmp_path,
    )
    monkeypatch.setattr(
        "app.services.skill_service.SkillRegistry.load_builtin",
        lambda _registry, _skills_dir: None,
    )
    svc = SkillService(FakeAgentProfileRepo())

    skills = await svc.list_skills("emp-1")

    assert skills == []

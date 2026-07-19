from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.skill_service import SkillService
from engine.skill.loader import SkillBody, SkillMeta


class FakeAgentProfileRepo:
    async def get(self, agent_id: str) -> dict | None:
        return {"id": agent_id, "name": "Smith"}


class FakeSkillRegistry:
    body = SkillBody(meta=SkillMeta(name="research", description="Research a topic."), content="Research.")

    def get(self, name: str) -> SkillBody | None:
        return self.body if name == self.body.meta.name else None

    def is_builtin(self, name: str) -> bool:
        return name == self.body.meta.name

    def list_summaries(self) -> list[dict[str, str]]:
        return [{"name": self.body.meta.name, "source": "builtin"}]


@pytest.mark.asyncio
async def test_list_skills_allows_an_empty_single_smith_skill_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "app.services.skill_service.AGENT_DIR",
        tmp_path,
    )
    monkeypatch.setattr(
        "app.services.skill_service.SkillRegistry.load_builtin",
        lambda _registry, _skills_dir: None,
    )
    svc = SkillService(FakeAgentProfileRepo())

    skills = await svc.list_skills("smith-id")

    assert skills == []


@pytest.mark.asyncio
async def test_skill_enablement_is_persisted_and_exposed_in_the_catalog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("app.services.skill_service.AGENT_DIR", tmp_path)
    monkeypatch.setattr(SkillService, "_load_registry", staticmethod(FakeSkillRegistry))
    svc = SkillService(FakeAgentProfileRepo())

    disabled = await svc.set_skill_enabled("smith-id", "research", False)
    assert disabled.enabled is False
    assert (tmp_path / "skills.yaml").is_file()
    assert (await svc.list_skills("smith-id"))[0].enabled is False

    enabled = await svc.set_skill_enabled("smith-id", "research", True)
    assert enabled.enabled is True
    assert (await svc.list_skills("smith-id"))[0].enabled is True

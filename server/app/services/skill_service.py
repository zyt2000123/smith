from __future__ import annotations

from fastapi import HTTPException

from engine.skill.registry import SkillRegistry

from ..schemas.skill import SkillSummaryOut
from common.config import AGENT_DIR, PATHS
from ..infrastructure.repositories.agent_profile_repo import AgentProfileRepo


class SkillService:

    def __init__(self, agent_profile_repo: AgentProfileRepo) -> None:
        self.agent_profile_repo = agent_profile_repo

    async def list_skills(self, agent_id: str) -> list[SkillSummaryOut]:
        await self._ensure_profile(agent_id)
        registry = self._load_registry()

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

    async def ensure_skill_exists(self, agent_id: str, skill_name: str) -> SkillSummaryOut:
        await self._ensure_profile(agent_id)
        registry = self._load_registry()
        body = registry.get(skill_name)
        if body is None:
            raise HTTPException(404, f"Skill '{skill_name}' not found")

        source = "builtin" if registry.is_builtin(skill_name) else "agent"
        return SkillSummaryOut(
            name=body.meta.name,
            description=body.meta.description,
            source=source,
            version=body.meta.version,
            argument_hint=body.meta.argument_hint,
        )

    async def _ensure_profile(self, agent_id: str) -> None:
        if await self.agent_profile_repo.get(agent_id) is None:
            raise HTTPException(404, "Agent profile not found")

    @staticmethod
    def _load_registry() -> SkillRegistry:
        registry = SkillRegistry()
        # PATHS.project_root honors AGENT_SMITH_PROJECT_ROOT, matching engine_runtime.
        registry.load_builtin(PATHS.project_root / "agents" / "skills")

        agent_skills_dir = AGENT_DIR / "skills"
        if agent_skills_dir.is_dir():
            registry.load_agent_skills(agent_skills_dir)
        return registry

from fastapi import APIRouter, Depends

from ..schemas.skill import SkillSummaryOut
from ..infrastructure.repositories.agent_profile_repo import AgentProfileRepo
from ..services.skill_service import SkillService

router = APIRouter(
    prefix="/api/agents/{agent_id}/skills",
    tags=["legacy-skills"],
    include_in_schema=False,
)


def get_skill_service() -> SkillService:
    return SkillService(AgentProfileRepo())


@router.get("", response_model=list[SkillSummaryOut])
async def list_skills(agent_id: str, svc: SkillService = Depends(get_skill_service)):
    return await svc.list_skills(agent_id)

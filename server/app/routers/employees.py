from fastapi import APIRouter, Depends

from ..schemas.agent_profile import AgentProfileCreate, AgentProfileUpdate, AgentProfileOut
from ..services.agent_profile_service import AgentProfileService
from ..infrastructure.repositories.agent_profile_repo import AgentProfileRepo

router = APIRouter(
    prefix="/api/agents",
    tags=["legacy-agents"],
    include_in_schema=False,
)


def get_agent_profile_service() -> AgentProfileService:
    return AgentProfileService(AgentProfileRepo())


@router.get("", response_model=list[AgentProfileOut])
async def list_profiles(svc: AgentProfileService = Depends(get_agent_profile_service)):
    return await svc.list_profiles()


@router.post("", response_model=AgentProfileOut, status_code=201)
async def create_profile(body: AgentProfileCreate, svc: AgentProfileService = Depends(get_agent_profile_service)):
    return await svc.create_profile(body)


@router.get("/{agent_id}", response_model=AgentProfileOut)
async def get_profile(agent_id: str, svc: AgentProfileService = Depends(get_agent_profile_service)):
    return await svc.get_profile(agent_id)


@router.put("/{agent_id}", response_model=AgentProfileOut)
async def update_profile(agent_id: str, body: AgentProfileUpdate, svc: AgentProfileService = Depends(get_agent_profile_service)):
    return await svc.update_profile(agent_id, body)


@router.delete("/{agent_id}", status_code=204)
async def delete_profile(agent_id: str, svc: AgentProfileService = Depends(get_agent_profile_service)):
    await svc.delete_profile(agent_id)

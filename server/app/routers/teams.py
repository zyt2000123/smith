from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from ..domain.team import TeamGroupCreate, TeamGroupOut, TeamMessageCreate, TeamMessageOut
from ..services.team_service import TeamService
from ..infrastructure.repositories.team_repo import TeamRepo
from ..infrastructure.repositories.employee_repo import EmployeeRepo

router = APIRouter(prefix="/api/teams", tags=["teams"])


def get_team_service() -> TeamService:
    return TeamService(TeamRepo(), EmployeeRepo())


@router.post("", response_model=TeamGroupOut, status_code=201)
async def create_group(body: TeamGroupCreate, svc: TeamService = Depends(get_team_service)):
    return await svc.create_group(body.name, body.description, body.member_ids)


@router.get("", response_model=list[TeamGroupOut])
async def list_groups(svc: TeamService = Depends(get_team_service)):
    return await svc.list_groups()


@router.get("/{group_id}", response_model=TeamGroupOut)
async def get_group(group_id: str, svc: TeamService = Depends(get_team_service)):
    return await svc.get_group(group_id)


@router.delete("/{group_id}", status_code=204)
async def delete_group(group_id: str, svc: TeamService = Depends(get_team_service)):
    await svc.delete_group(group_id)


@router.get("/{group_id}/messages", response_model=list[TeamMessageOut])
async def list_messages(group_id: str, limit: int = 50, svc: TeamService = Depends(get_team_service)):
    return await svc.get_messages(group_id, limit=limit)


@router.post("/{group_id}/messages", response_model=list[TeamMessageOut], status_code=201)
async def send_message(group_id: str, body: TeamMessageCreate, svc: TeamService = Depends(get_team_service)):
    return await svc.send_message(group_id, body.content)


@router.post("/{group_id}/messages/stream")
async def stream_message(group_id: str, body: TeamMessageCreate, svc: TeamService = Depends(get_team_service)):
    return EventSourceResponse(svc.stream_message(group_id, body.content))

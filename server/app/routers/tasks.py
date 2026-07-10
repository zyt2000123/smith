from fastapi import APIRouter, Depends

from ..schemas.task import TaskCreate, TaskOut
from ..services.task_service import TaskService
from ..infrastructure.repositories.task_repo import TaskRepo
from ..infrastructure.repositories.agent_profile_repo import AgentProfileRepo

router = APIRouter(
    prefix="/api/agents/{agent_id}/tasks",
    tags=["legacy-tasks"],
    include_in_schema=False,
)


def get_task_service() -> TaskService:
    return TaskService(TaskRepo(), AgentProfileRepo())


@router.get("", response_model=list[TaskOut])
async def list_tasks(agent_id: str, svc: TaskService = Depends(get_task_service)):
    return await svc.list_tasks(agent_id)


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(agent_id: str, body: TaskCreate, svc: TaskService = Depends(get_task_service)):
    return await svc.create_task(agent_id, body)

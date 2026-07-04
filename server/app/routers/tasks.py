from fastapi import APIRouter, Depends

from ..domain.task import TaskCreate, TaskOut
from ..services.task_service import TaskService
from ..infrastructure.repositories.task_repo import TaskRepo
from ..infrastructure.repositories.employee_repo import EmployeeRepo

router = APIRouter(prefix="/api/employees/{employee_id}/tasks", tags=["tasks"])


def get_task_service() -> TaskService:
    return TaskService(TaskRepo(), EmployeeRepo())


@router.get("", response_model=list[TaskOut])
async def list_tasks(employee_id: str, svc: TaskService = Depends(get_task_service)):
    return await svc.list_tasks(employee_id)


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(employee_id: str, body: TaskCreate, svc: TaskService = Depends(get_task_service)):
    return await svc.create_task(employee_id, body)

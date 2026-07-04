from fastapi import APIRouter, Depends

from ..domain.auto_task import (
    AutoTaskCreate,
    AutoTaskUpdate,
    AutoTaskOut,
    AutoTaskRunOut,
)
from ..services.auto_task_service import AutoTaskService
from ..infrastructure.repositories.auto_task_repo import AutoTaskRepo
from ..infrastructure.repositories.employee_repo import EmployeeRepo
from ..infrastructure.repositories.session_repo import SessionRepo

router = APIRouter(
    prefix="/api/employees/{employee_id}/auto-tasks", tags=["auto-tasks"]
)


def get_service() -> AutoTaskService:
    return AutoTaskService(AutoTaskRepo(), EmployeeRepo(), SessionRepo())


@router.get("", response_model=list[AutoTaskOut])
async def list_auto_tasks(
    employee_id: str, svc: AutoTaskService = Depends(get_service)
):
    return await svc.list_auto_tasks(employee_id)


@router.post("", response_model=AutoTaskOut, status_code=201)
async def create_auto_task(
    employee_id: str,
    body: AutoTaskCreate,
    svc: AutoTaskService = Depends(get_service),
):
    return await svc.create_auto_task(employee_id, body)


@router.put("/{task_id}", response_model=AutoTaskOut)
async def update_auto_task(
    employee_id: str,
    task_id: str,
    body: AutoTaskUpdate,
    svc: AutoTaskService = Depends(get_service),
):
    return await svc.update_auto_task(task_id, body)


@router.post("/{task_id}/trigger", response_model=AutoTaskRunOut)
async def trigger_auto_task(
    employee_id: str,
    task_id: str,
    svc: AutoTaskService = Depends(get_service),
):
    return await svc.trigger_auto_task(task_id)


@router.delete("/{task_id}", status_code=204)
async def delete_auto_task(
    employee_id: str,
    task_id: str,
    svc: AutoTaskService = Depends(get_service),
):
    await svc.delete_auto_task(task_id)


@router.get("/{task_id}/runs", response_model=list[AutoTaskRunOut])
async def list_runs(
    employee_id: str,
    task_id: str,
    svc: AutoTaskService = Depends(get_service),
):
    return await svc.list_runs(task_id)

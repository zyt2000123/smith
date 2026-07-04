from __future__ import annotations

from fastapi import HTTPException

from ..domain.task import TaskCreate, TaskOut
from ..infrastructure.repositories.task_repo import TaskRepo
from ..infrastructure.repositories.employee_repo import EmployeeRepo


class TaskService:

    def __init__(self, task_repo: TaskRepo, employee_repo: EmployeeRepo) -> None:
        self.task_repo = task_repo
        self.employee_repo = employee_repo

    async def list_tasks(self, employee_id: str) -> list[TaskOut]:
        rows = await self.task_repo.list_by_employee(employee_id)
        return [TaskOut(**r) for r in rows]

    async def create_task(self, employee_id: str, body: TaskCreate) -> TaskOut:
        emp = await self.employee_repo.get(employee_id)
        if emp is None:
            raise HTTPException(404, "Employee not found")
        row = await self.task_repo.create(employee_id, body.type, body.title)
        return TaskOut(**row)

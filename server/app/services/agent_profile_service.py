from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from common.config import TEMPLATES_DIR
from common.filesystem import init_employee_files, delete_employee_files

from ..domain.employee import EmployeeCreate, EmployeeUpdate, EmployeeOut
from ..infrastructure.repositories.employee_repo import EmployeeRepo


class EmployeeService:

    def __init__(self, repo: EmployeeRepo) -> None:
        self.repo = repo

    async def list_employees(self) -> list[EmployeeOut]:
        rows = await self.repo.list_all()
        return [EmployeeOut(**r) for r in rows]

    async def get_employee(self, employee_id: str) -> EmployeeOut:
        row = await self.repo.get(employee_id)
        if row is None:
            raise HTTPException(404, "Employee not found")
        return EmployeeOut(**row)

    async def create_employee(self, body: EmployeeCreate) -> EmployeeOut:
        template_dir = TEMPLATES_DIR / body.role
        data = body.model_dump()
        row = await self.repo.create(data)
        init_employee_files(
            row["id"],
            template_dir=template_dir,
            name=body.name,
            role=body.role,
            description=body.description,
        )
        return EmployeeOut(**row)

    async def update_employee(self, employee_id: str, body: EmployeeUpdate) -> EmployeeOut:
        updates = body.model_dump(exclude_none=True)
        row = await self.repo.update(employee_id, updates)
        if row is None:
            raise HTTPException(404, "Employee not found")
        return EmployeeOut(**row)

    async def delete_employee(self, employee_id: str) -> None:
        deleted = await self.repo.delete(employee_id)
        if not deleted:
            raise HTTPException(404, "Employee not found")
        delete_employee_files(employee_id)

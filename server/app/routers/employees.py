from fastapi import APIRouter, Depends

from ..domain.employee import EmployeeCreate, EmployeeUpdate, EmployeeOut
from ..services.employee_service import EmployeeService
from ..infrastructure.repositories.employee_repo import EmployeeRepo

router = APIRouter(prefix="/api/employees", tags=["employees"])


def get_employee_service() -> EmployeeService:
    return EmployeeService(EmployeeRepo())


@router.get("", response_model=list[EmployeeOut])
async def list_employees(svc: EmployeeService = Depends(get_employee_service)):
    return await svc.list_employees()


@router.post("", response_model=EmployeeOut, status_code=201)
async def create_employee(body: EmployeeCreate, svc: EmployeeService = Depends(get_employee_service)):
    return await svc.create_employee(body)


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(employee_id: str, svc: EmployeeService = Depends(get_employee_service)):
    return await svc.get_employee(employee_id)


@router.put("/{employee_id}", response_model=EmployeeOut)
async def update_employee(employee_id: str, body: EmployeeUpdate, svc: EmployeeService = Depends(get_employee_service)):
    return await svc.update_employee(employee_id, body)


@router.delete("/{employee_id}", status_code=204)
async def delete_employee(employee_id: str, svc: EmployeeService = Depends(get_employee_service)):
    await svc.delete_employee(employee_id)

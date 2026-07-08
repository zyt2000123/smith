from fastapi import APIRouter, Depends

from ..domain.skill import SkillSummaryOut
from ..infrastructure.repositories.employee_repo import EmployeeRepo
from ..services.skill_service import SkillService

router = APIRouter(prefix="/api/employees/{employee_id}/skills", tags=["skills"])


def get_skill_service() -> SkillService:
    return SkillService(EmployeeRepo())


@router.get("", response_model=list[SkillSummaryOut])
async def list_skills(employee_id: str, svc: SkillService = Depends(get_skill_service)):
    return await svc.list_skills(employee_id)

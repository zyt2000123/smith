from fastapi import APIRouter, HTTPException

from ..services.stats_service import StatsService

router = APIRouter(prefix="/api/employees/{employee_id}/stats", tags=["stats"])


@router.get("")
async def get_stats(employee_id: str):
    svc = StatsService()
    result = await svc.get_employee_stats(employee_id)
    if result is None:
        raise HTTPException(404, "Employee not found")
    return result

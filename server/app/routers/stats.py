from fastapi import APIRouter

from ..services.stats_service import StatsService

router = APIRouter(
    prefix="/api/agents/{agent_id}/stats",
    tags=["legacy-stats"],
    include_in_schema=False,
)


@router.get("")
async def get_stats(agent_id: str):
    return await StatsService().get_agent_stats(agent_id)

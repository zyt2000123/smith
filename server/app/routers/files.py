from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..services.profile_file_service import ProfileFileService

router = APIRouter(
    prefix="/api/agents/{agent_id}/files",
    tags=["legacy-files"],
    include_in_schema=False,
)


class FileContent(BaseModel):
    content: str


def get_profile_file_service() -> ProfileFileService:
    return ProfileFileService()


@router.get("")
async def list_files(
    agent_id: str,
    svc: ProfileFileService = Depends(get_profile_file_service),
):
    return await svc.list_files(agent_id)


@router.get("/{filename}")
async def get_file(
    agent_id: str,
    filename: str,
    svc: ProfileFileService = Depends(get_profile_file_service),
):
    return await svc.get_file(agent_id, filename)


@router.put("/{filename}")
async def update_file(
    agent_id: str,
    filename: str,
    body: FileContent,
    svc: ProfileFileService = Depends(get_profile_file_service),
):
    return await svc.update_file(agent_id, filename, body.content)

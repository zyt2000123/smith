from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..schemas.agent_profile import AgentProfileOut, AgentProfileUpdate
from ..schemas.auto_task import (
    AutoTaskCreate,
    AutoTaskOut,
    AutoTaskRunOut,
    AutoTaskUpdate,
)
from ..schemas.session import MessageCreate, MessageOut, SessionCreate, SessionOut
from ..schemas.skill import SkillSummaryOut
from ..schemas.task import TaskCreate, TaskOut
from ..services.agent_service import AgentService

router = APIRouter(prefix="/api/agent", tags=["agent"])


class FileContent(BaseModel):
    content: str


def get_agent_service() -> AgentService:
    return AgentService()


@router.get("", response_model=AgentProfileOut)
async def get_profile(svc: AgentService = Depends(get_agent_service)):
    return await svc.get_profile()


@router.post("/ensure", response_model=AgentProfileOut, status_code=201)
async def ensure_profile(svc: AgentService = Depends(get_agent_service)):
    return await svc.ensure_profile()


@router.put("", response_model=AgentProfileOut)
async def update_profile(
    body: AgentProfileUpdate,
    svc: AgentService = Depends(get_agent_service),
):
    return await svc.update_profile(body)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(svc: AgentService = Depends(get_agent_service)):
    return await svc.list_sessions()


@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_session(
    body: SessionCreate,
    svc: AgentService = Depends(get_agent_service),
):
    return await svc.create_session(body.title, body.identity_id)


@router.get("/identities")
async def list_identities(svc: AgentService = Depends(get_agent_service)):
    """Expose the startup-scanned identity catalog for clients and CLI users."""
    return await svc.list_identities()


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(
    session_id: str,
    limit: int = 0,
    offset: int = 0,
    svc: AgentService = Depends(get_agent_service),
):
    return await svc.list_messages(session_id, limit=limit, offset=offset)


@router.post("/sessions/{session_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(
    session_id: str,
    body: MessageCreate,
    svc: AgentService = Depends(get_agent_service),
):
    return await svc.send_message(
        session_id,
        body.content,
        context=body.context,
        skill_name=body.skill_name,
        identity_id=body.identity_id,
        working_dir=body.working_dir,
    )


@router.post("/sessions/{session_id}/messages/stream")
async def stream_message(
    session_id: str,
    body: MessageCreate,
    svc: AgentService = Depends(get_agent_service),
):
    return EventSourceResponse(
        svc.stream_message(
            session_id,
            body.content,
            context=body.context,
            skill_name=body.skill_name,
            identity_id=body.identity_id,
            working_dir=body.working_dir,
        )
    )


@router.get("/skills", response_model=list[SkillSummaryOut])
async def list_skills(svc: AgentService = Depends(get_agent_service)):
    return await svc.list_skills()


@router.get("/files")
async def list_files(svc: AgentService = Depends(get_agent_service)):
    return await svc.list_files()


@router.get("/files/{filename}")
async def get_file(
    filename: str,
    svc: AgentService = Depends(get_agent_service),
):
    return await svc.get_file(filename)


@router.put("/files/{filename}")
async def update_file(
    filename: str,
    body: FileContent,
    svc: AgentService = Depends(get_agent_service),
):
    return await svc.update_file(filename, body.content)


@router.get("/stats")
async def get_stats(svc: AgentService = Depends(get_agent_service)):
    return await svc.get_stats()


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(svc: AgentService = Depends(get_agent_service)):
    return await svc.list_tasks()


@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    body: TaskCreate,
    svc: AgentService = Depends(get_agent_service),
):
    return await svc.create_task(body)


@router.get("/auto-tasks", response_model=list[AutoTaskOut])
async def list_auto_tasks(svc: AgentService = Depends(get_agent_service)):
    return await svc.list_auto_tasks()


@router.post("/auto-tasks", response_model=AutoTaskOut, status_code=201)
async def create_auto_task(
    body: AutoTaskCreate,
    svc: AgentService = Depends(get_agent_service),
):
    return await svc.create_auto_task(body)


@router.put("/auto-tasks/{task_id}", response_model=AutoTaskOut)
async def update_auto_task(
    task_id: str,
    body: AutoTaskUpdate,
    svc: AgentService = Depends(get_agent_service),
):
    return await svc.update_auto_task(task_id, body)


@router.post("/auto-tasks/{task_id}/trigger", response_model=AutoTaskRunOut)
async def trigger_auto_task(
    task_id: str,
    svc: AgentService = Depends(get_agent_service),
):
    return await svc.trigger_auto_task(task_id)


@router.delete("/auto-tasks/{task_id}", status_code=204)
async def delete_auto_task(
    task_id: str,
    svc: AgentService = Depends(get_agent_service),
):
    await svc.delete_auto_task(task_id)


@router.get("/auto-tasks/{task_id}/runs", response_model=list[AutoTaskRunOut])
async def list_runs(
    task_id: str,
    svc: AgentService = Depends(get_agent_service),
):
    return await svc.list_runs(task_id)

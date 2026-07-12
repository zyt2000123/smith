from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from ..schemas.session import SessionCreate, SessionOut, MessageCreate, MessageOut
from ..services.session_service import SessionService
from ..infrastructure.repositories.session_repo import SessionRepo
from ..infrastructure.repositories.agent_profile_repo import AgentProfileRepo

router = APIRouter(
    prefix="/api/agents/{agent_id}/sessions",
    tags=["legacy-sessions"],
    include_in_schema=False,
)


def get_session_service() -> SessionService:
    return SessionService(SessionRepo(), AgentProfileRepo())


@router.get("", response_model=list[SessionOut])
async def list_sessions(agent_id: str, svc: SessionService = Depends(get_session_service)):
    return await svc.list_sessions(agent_id)


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(agent_id: str, body: SessionCreate, svc: SessionService = Depends(get_session_service)):
    return await svc.create_session(agent_id, body.title)


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(agent_id: str, session_id: str, limit: int = 0, offset: int = 0, svc: SessionService = Depends(get_session_service)):
    return await svc.list_messages(session_id, limit=limit, offset=offset)


@router.post("/{session_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(agent_id: str, session_id: str, body: MessageCreate, svc: SessionService = Depends(get_session_service)):
    return await svc.send_message(
        agent_id,
        session_id,
        body.content,
        context=body.context,
        skill_name=body.skill_name,
        working_dir=body.working_dir,
    )


@router.post("/{session_id}/messages/stream")
async def stream_message(agent_id: str, session_id: str, body: MessageCreate, svc: SessionService = Depends(get_session_service)):
    return EventSourceResponse(
        svc.stream_message(
            agent_id,
            session_id,
            body.content,
            context=body.context,
            skill_name=body.skill_name,
            working_dir=body.working_dir,
        )
    )

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from ..domain.session import SessionCreate, SessionOut, MessageCreate, MessageOut
from ..services.session_service import SessionService
from ..infrastructure.repositories.session_repo import SessionRepo
from ..infrastructure.repositories.employee_repo import EmployeeRepo

router = APIRouter(prefix="/api/employees/{employee_id}/sessions", tags=["sessions"])


def get_session_service() -> SessionService:
    return SessionService(SessionRepo(), EmployeeRepo())


@router.get("", response_model=list[SessionOut])
async def list_sessions(employee_id: str, svc: SessionService = Depends(get_session_service)):
    return await svc.list_sessions(employee_id)


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(employee_id: str, body: SessionCreate, svc: SessionService = Depends(get_session_service)):
    return await svc.create_session(employee_id, body.title)


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(employee_id: str, session_id: str, limit: int = 0, offset: int = 0, svc: SessionService = Depends(get_session_service)):
    return await svc.list_messages(session_id, limit=limit, offset=offset)


@router.post("/{session_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(employee_id: str, session_id: str, body: MessageCreate, svc: SessionService = Depends(get_session_service)):
    return await svc.send_message(employee_id, session_id, body.content)


@router.post("/{session_id}/messages/stream")
async def stream_message(employee_id: str, session_id: str, body: MessageCreate, svc: SessionService = Depends(get_session_service)):
    return EventSourceResponse(svc.stream_message(employee_id, session_id, body.content))

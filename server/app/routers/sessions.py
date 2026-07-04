import json, uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse
from ..db import get_db
from ..models.session import SessionCreate, SessionOut, MessageCreate, MessageOut
from ..agent_runtime import run_agent_reply, stream_agent_reply
from ..employee_fs import read_employee_file

router = APIRouter(prefix="/api/employees/{employee_id}/sessions", tags=["sessions"])


async def _get_system_prompt(employee_id: str) -> str:
    """Build system prompt from employee identity + persona files."""
    identity = read_employee_file(employee_id, "identity.md") or ""
    persona = read_employee_file(employee_id, "persona.md") or ""
    bible = read_employee_file(employee_id, "bible.md") or ""
    parts = [p for p in [identity, persona, bible] if p.strip()]
    return "\n\n---\n\n".join(parts) if parts else "你是一个Agent。"


@router.get("", response_model=list[SessionOut])
async def list_sessions(employee_id: str):
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM sessions WHERE employee_id=? ORDER BY created_at DESC", (employee_id,))
    return [SessionOut(**dict(r)) for r in rows]


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(employee_id: str, body: SessionCreate):
    db = await get_db()
    emp = await db.execute_fetchall("SELECT id FROM employees WHERE id=?", (employee_id,))
    if not emp:
        raise HTTPException(404, "Employee not found")
    sid = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO sessions (id, employee_id, title, created_at) VALUES (?,?,?,?)",
        (sid, employee_id, body.title or "新对话", now))
    await db.commit()
    return SessionOut(id=sid, employee_id=employee_id, title=body.title or "新对话", created_at=now)


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(employee_id: str, session_id: str):
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC", (session_id,))
    return [MessageOut(**dict(r)) for r in rows]


@router.post("/{session_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(employee_id: str, session_id: str, body: MessageCreate):
    """Send a message and get an AgentScope-powered reply."""
    db = await get_db()
    sess = await db.execute_fetchall("SELECT id FROM sessions WHERE id=? AND employee_id=?", (session_id, employee_id))
    if not sess:
        raise HTTPException(404, "Session not found")

    emp_rows = await db.execute_fetchall("SELECT name FROM employees WHERE id=?", (employee_id,))
    emp_name = emp_rows[0]["name"] if emp_rows else "Agent"

    now = datetime.now(timezone.utc).isoformat()

    # Save user message
    user_msg_id = uuid.uuid4().hex[:12]
    await db.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
        (user_msg_id, session_id, "user", body.content, now))

    # Get AgentScope reply
    system_prompt = await _get_system_prompt(employee_id)
    reply_text = await run_agent_reply(employee_id, emp_name, system_prompt, body.content)

    # Save assistant message
    assistant_msg_id = uuid.uuid4().hex[:12]
    reply_time = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
        (assistant_msg_id, session_id, "assistant", reply_text, reply_time))
    await db.commit()

    return MessageOut(id=assistant_msg_id, session_id=session_id, role="assistant",
                      content=reply_text, created_at=reply_time)


@router.post("/{session_id}/messages/stream")
async def stream_message(employee_id: str, session_id: str, body: MessageCreate):
    """Send a message and stream the AgentScope reply via SSE."""
    db = await get_db()
    sess = await db.execute_fetchall("SELECT id FROM sessions WHERE id=? AND employee_id=?", (session_id, employee_id))
    if not sess:
        raise HTTPException(404, "Session not found")

    emp_rows = await db.execute_fetchall("SELECT name FROM employees WHERE id=?", (employee_id,))
    emp_name = emp_rows[0]["name"] if emp_rows else "Agent"

    now = datetime.now(timezone.utc).isoformat()
    user_msg_id = uuid.uuid4().hex[:12]
    await db.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
        (user_msg_id, session_id, "user", body.content, now))
    await db.commit()

    system_prompt = await _get_system_prompt(employee_id)

    async def event_generator():
        full_reply = []
        async for chunk in stream_agent_reply(employee_id, emp_name, system_prompt, body.content):
            full_reply.append(chunk)
            yield {"event": "message", "data": json.dumps({"text": chunk}, ensure_ascii=False)}

        # Save complete reply
        reply_text = "".join(full_reply)
        assistant_msg_id = uuid.uuid4().hex[:12]
        reply_time = datetime.now(timezone.utc).isoformat()
        db2 = await get_db()
        await db2.execute(
            "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
            (assistant_msg_id, session_id, "assistant", reply_text, reply_time))
        await db2.commit()
        yield {"event": "done", "data": json.dumps({"id": assistant_msg_id}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())

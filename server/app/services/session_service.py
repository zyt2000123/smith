from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import HTTPException

from common.filesystem import read_employee_file
from engine.execution.agent_loop import reply as engine_reply, reply_stream as engine_reply_stream

from ..domain.session import SessionOut, MessageOut
from ..infrastructure.repositories.session_repo import SessionRepo
from ..infrastructure.repositories.employee_repo import EmployeeRepo


class SessionService:

    def __init__(self, session_repo: SessionRepo, employee_repo: EmployeeRepo) -> None:
        self.session_repo = session_repo
        self.employee_repo = employee_repo

    async def list_sessions(self, employee_id: str) -> list[SessionOut]:
        rows = await self.session_repo.list_by_employee(employee_id)
        return [SessionOut(**r) for r in rows]

    async def create_session(self, employee_id: str, title: str) -> SessionOut:
        emp = await self.employee_repo.get(employee_id)
        if emp is None:
            raise HTTPException(404, "Employee not found")
        row = await self.session_repo.create(employee_id, title or "新对话")
        return SessionOut(**row)

    async def list_messages(self, session_id: str, limit: int = 0, offset: int = 0) -> list[MessageOut]:
        rows = await self.session_repo.get_messages(session_id, limit=limit, offset=offset)
        return [MessageOut(**r) for r in rows]

    async def send_message(
        self, employee_id: str, session_id: str, content: str
    ) -> MessageOut:
        if not await self.session_repo.exists(session_id, employee_id):
            raise HTTPException(404, "Session not found")

        emp = await self.employee_repo.get(employee_id)
        emp_name = emp["name"] if emp else "Agent"

        # Save user message
        await self.session_repo.add_message(session_id, "user", content)

        # Call engine
        reply_text = await engine_reply(employee_id, emp_name, content)

        # Save assistant message
        msg = await self.session_repo.add_message(session_id, "assistant", reply_text)
        return MessageOut(**msg)

    async def stream_message(
        self, employee_id: str, session_id: str, content: str
    ) -> AsyncGenerator[dict, None]:
        """Yield SSE event dicts. Streams text chunks as they arrive from the engine."""
        if not await self.session_repo.exists(session_id, employee_id):
            raise HTTPException(404, "Session not found")

        emp = await self.employee_repo.get(employee_id)
        emp_name = emp["name"] if emp else "Agent"

        # Save user message
        await self.session_repo.add_message(session_id, "user", content)

        # Stream from engine
        full_reply = []
        async for chunk in engine_reply_stream(employee_id, emp_name, content):
            full_reply.append(chunk)
            yield {"event": "message", "data": json.dumps({"text": chunk}, ensure_ascii=False)}

        # Save the complete assistant message
        reply_text = "".join(full_reply)
        msg = await self.session_repo.add_message(session_id, "assistant", reply_text)

        yield {"event": "done", "data": json.dumps({"id": msg["id"]}, ensure_ascii=False)}

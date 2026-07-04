from __future__ import annotations

import uuid
from datetime import datetime, timezone

from common.database import get_db


class TaskRepo:

    async def list_by_employee(self, employee_id: str) -> list[dict]:
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM tasks WHERE employee_id=? ORDER BY created_at DESC",
            (employee_id,),
        )
        return [dict(r) for r in rows]

    async def create(self, employee_id: str, type: str, title: str) -> dict:
        db = await get_db()
        tid = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO tasks (id, employee_id, type, title, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (tid, employee_id, type, title, "pending", now, now),
        )
        await db.commit()
        return {
            "id": tid,
            "employee_id": employee_id,
            "type": type,
            "title": title,
            "status": "pending",
            "session_id": None,
            "created_at": now,
            "updated_at": now,
        }

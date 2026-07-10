from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..database import get_app_db


class TaskRepo:

    async def list_by_agent(self, agent_id: str) -> list[dict]:
        db = await get_app_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM tasks WHERE agent_id=? ORDER BY created_at DESC",
            (agent_id,),
        )
        return [dict(r) for r in rows]

    async def create(self, agent_id: str, type: str, title: str) -> dict:
        db = await get_app_db()
        tid = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO tasks (id, agent_id, type, title, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (tid, agent_id, type, title, "pending", now, now),
        )
        await db.commit()
        return {
            "id": tid,
            "agent_id": agent_id,
            "type": type,
            "title": title,
            "status": "pending",
            "session_id": None,
            "created_at": now,
            "updated_at": now,
        }

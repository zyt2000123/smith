from __future__ import annotations

import uuid
from datetime import datetime, timezone

from common.database import get_db


class SessionRepo:

    async def list_by_employee(self, employee_id: str) -> list[dict]:
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT s.id, s.employee_id, s.title, s.created_at, "
            "  (SELECT content FROM messages m WHERE m.session_id=s.id ORDER BY m.created_at DESC LIMIT 1) as last_message_preview, "
            "  (SELECT created_at FROM messages m WHERE m.session_id=s.id ORDER BY m.created_at DESC LIMIT 1) as last_message_at, "
            "  (SELECT count(*) FROM messages m WHERE m.session_id=s.id) as message_count "
            "FROM sessions s WHERE s.employee_id=? ORDER BY s.created_at DESC",
            (employee_id,),
        )
        result = []
        for r in rows:
            d = dict(r)
            preview = d.get("last_message_preview") or ""
            if len(preview) > 100:
                d["last_message_preview"] = preview[:100] + "..."
            result.append(d)
        return result

    async def create(self, employee_id: str, title: str) -> dict:
        db = await get_db()
        sid = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO sessions (id, employee_id, title, created_at) VALUES (?,?,?,?)",
            (sid, employee_id, title, now),
        )
        await db.commit()
        return {"id": sid, "employee_id": employee_id, "title": title, "created_at": now}

    async def exists(self, session_id: str, employee_id: str) -> bool:
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT id FROM sessions WHERE id=? AND employee_id=?",
            (session_id, employee_id),
        )
        return bool(rows)

    async def get_messages(self, session_id: str, limit: int = 0, offset: int = 0) -> list[dict]:
        db = await get_db()
        if limit > 0:
            rows = await db.execute_fetchall(
                "SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC LIMIT ? OFFSET ?",
                (session_id, limit, offset),
            )
        else:
            rows = await db.execute_fetchall(
                "SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC",
                (session_id,),
            )
        return [dict(r) for r in rows]

    async def add_message(self, session_id: str, role: str, content: str) -> dict:
        db = await get_db()
        mid = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
            (mid, session_id, role, content, now),
        )
        await db.commit()
        return {"id": mid, "session_id": session_id, "role": role, "content": content, "created_at": now}

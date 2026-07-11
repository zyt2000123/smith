from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..database import get_app_db


class SessionRepo:

    async def list_by_agent(self, agent_id: str) -> list[dict]:
        db = await get_app_db()
        rows = await db.execute_fetchall(
            "SELECT s.id, s.agent_id, s.identity_id, s.title, s.created_at, "
            "  (SELECT content FROM messages m WHERE m.session_id=s.id ORDER BY m.created_at DESC LIMIT 1) as last_message_preview, "
            "  (SELECT created_at FROM messages m WHERE m.session_id=s.id ORDER BY m.created_at DESC LIMIT 1) as last_message_at, "
            "  (SELECT count(*) FROM messages m WHERE m.session_id=s.id) as message_count "
            "FROM sessions s WHERE s.agent_id=? ORDER BY s.created_at DESC",
            (agent_id,),
        )
        result = []
        for r in rows:
            d = dict(r)
            preview = d.get("last_message_preview") or ""
            if len(preview) > 100:
                d["last_message_preview"] = preview[:100] + "..."
            result.append(d)
        return result

    async def create(self, agent_id: str, title: str, identity_id: str | None = None) -> dict:
        db = await get_app_db()
        sid = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO sessions (id, agent_id, identity_id, title, created_at) VALUES (?,?,?,?,?)",
            (sid, agent_id, identity_id, title, now),
        )
        await db.commit()
        return {
            "id": sid,
            "agent_id": agent_id,
            "identity_id": identity_id,
            "title": title,
            "created_at": now,
        }

    async def exists(self, session_id: str, agent_id: str) -> bool:
        db = await get_app_db()
        rows = await db.execute_fetchall(
            "SELECT id FROM sessions WHERE id=? AND agent_id=?",
            (session_id, agent_id),
        )
        return bool(rows)

    async def get_owned(self, session_id: str, agent_id: str) -> dict | None:
        db = await get_app_db()
        rows = await db.execute_fetchall(
            "SELECT id, agent_id, identity_id, title, created_at FROM sessions WHERE id=? AND agent_id=?",
            (session_id, agent_id),
        )
        return dict(rows[0]) if rows else None

    async def claim_identity(
        self,
        session_id: str,
        agent_id: str,
        identity_id: str,
    ) -> bool:
        """Pin an identity once; a concurrent caller cannot overwrite it."""
        db = await get_app_db()
        cursor = await db.execute(
            "UPDATE sessions SET identity_id=? "
            "WHERE id=? AND agent_id=? AND identity_id IS NULL",
            (identity_id, session_id, agent_id),
        )
        await db.commit()
        return cursor.rowcount == 1

    async def get_messages(self, session_id: str, limit: int = 0, offset: int = 0) -> list[dict]:
        db = await get_app_db()
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
        db = await get_app_db()
        mid = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
            (mid, session_id, role, content, now),
        )
        await db.commit()
        return {"id": mid, "session_id": session_id, "role": role, "content": content, "created_at": now}

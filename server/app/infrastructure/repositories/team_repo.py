from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from ..database import get_app_db


class TeamRepo:

    # ── Groups ──────────────────────────────────────────────

    async def create_group(self, name: str, description: str, member_ids: list[str]) -> dict:
        db = await get_app_db()
        gid = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc).isoformat()
        members_json = json.dumps(member_ids, ensure_ascii=False)

        await db.execute(
            "INSERT INTO team_groups (id, name, description, member_ids, created_at) "
            "VALUES (?,?,?,?,?)",
            (gid, name, description, members_json, now),
        )
        await db.commit()
        return {
            "id": gid,
            "name": name,
            "description": description,
            "member_ids": member_ids,
            "created_at": now,
        }

    async def get_group(self, group_id: str) -> dict | None:
        db = await get_app_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM team_groups WHERE id=?", (group_id,)
        )
        if not rows:
            return None
        return self._group_to_dict(rows[0])

    async def list_groups(self) -> list[dict]:
        db = await get_app_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM team_groups ORDER BY created_at DESC"
        )
        return [self._group_to_dict(r) for r in rows]

    async def delete_group(self, group_id: str) -> bool:
        db = await get_app_db()
        rows = await db.execute_fetchall(
            "SELECT id FROM team_groups WHERE id=?", (group_id,)
        )
        if not rows:
            return False
        await db.execute("DELETE FROM team_groups WHERE id=?", (group_id,))
        await db.commit()
        return True

    # ── Messages ────────────────────────────────────────────

    async def add_message(
        self,
        group_id: str,
        sender_id: str,
        sender_name: str,
        content: str,
        mentions: list[str],
    ) -> dict:
        db = await get_app_db()
        mid = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        mentions_json = json.dumps(mentions, ensure_ascii=False)

        await db.execute(
            "INSERT INTO team_messages "
            "(id, group_id, sender_id, sender_name, content, mentions, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (mid, group_id, sender_id, sender_name, content, mentions_json, now),
        )
        await db.commit()
        return {
            "id": mid,
            "group_id": group_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "content": content,
            "mentions": mentions,
            "created_at": now,
        }

    async def get_messages(self, group_id: str, limit: int = 50) -> list[dict]:
        db = await get_app_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM team_messages WHERE group_id=? "
            "ORDER BY created_at ASC LIMIT ?",
            (group_id, limit),
        )
        return [self._msg_to_dict(r) for r in rows]

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _group_to_dict(row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "member_ids": json.loads(row["member_ids"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _msg_to_dict(row) -> dict:
        return {
            "id": row["id"],
            "group_id": row["group_id"],
            "sender_id": row["sender_id"],
            "sender_name": row["sender_name"],
            "content": row["content"],
            "mentions": json.loads(row["mentions"]),
            "created_at": row["created_at"],
        }

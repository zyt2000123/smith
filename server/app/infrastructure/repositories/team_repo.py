from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from common.database import get_db


_TEAM_SCHEMA = """
CREATE TABLE IF NOT EXISTS team_groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    member_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS team_messages (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL REFERENCES team_groups(id) ON DELETE CASCADE,
    sender_id TEXT NOT NULL,
    sender_name TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    mentions TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_tables_ready = False


class TeamRepo:

    async def _ensure_tables(self) -> None:
        global _tables_ready
        if _tables_ready:
            return
        db = await get_db()
        await db.executescript(_TEAM_SCHEMA)
        _tables_ready = True

    # ── Groups ──────────────────────────────────────────────

    async def create_group(self, name: str, description: str, member_ids: list[str]) -> dict:
        await self._ensure_tables()
        db = await get_db()
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
        await self._ensure_tables()
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM team_groups WHERE id=?", (group_id,)
        )
        if not rows:
            return None
        return self._group_to_dict(rows[0])

    async def list_groups(self) -> list[dict]:
        await self._ensure_tables()
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM team_groups ORDER BY created_at DESC"
        )
        return [self._group_to_dict(r) for r in rows]

    async def delete_group(self, group_id: str) -> bool:
        await self._ensure_tables()
        db = await get_db()
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
        await self._ensure_tables()
        db = await get_db()
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
        await self._ensure_tables()
        db = await get_db()
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

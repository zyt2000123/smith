from __future__ import annotations

import json
import uuid
import socket
from datetime import datetime, timezone

from common.config import LEGACY_AGENT_PROFILES_DIR

from ..database import get_app_db


class AgentProfileRepo:

    async def list_all(self) -> list[dict]:
        db = await get_app_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM agent_profiles ORDER BY created_at DESC"
        )
        return [self._row_to_dict(r) for r in rows]

    async def get(self, agent_id: str) -> dict | None:
        db = await get_app_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM agent_profiles WHERE id=?", (agent_id,)
        )
        if not rows:
            return None
        return self._row_to_dict(rows[0])

    async def create(self, data: dict) -> dict:
        db = await get_app_db()
        eid = uuid.uuid4().hex[:8]
        device = data.get("device") or socket.gethostname()
        now = datetime.now(timezone.utc).isoformat()
        knowledge_json = json.dumps(
            data.get("knowledge", []), ensure_ascii=False
        )

        await db.execute(
            "INSERT INTO agent_profiles "
            "(id, name, role, device, online, description, knowledge, "
            "environment, accent, config_path, created_at) "
            "VALUES (?,?,?,?,1,?,?,?,?,?,?)",
            (
                eid,
                data["name"],
                data["role"],
                device,
                data.get("description", ""),
                knowledge_json,
                data.get("environment", "本地"),
                data.get("accent", ""),
                str(LEGACY_AGENT_PROFILES_DIR / eid),
                now,
            ),
        )
        await db.commit()

        return (await self.get(eid))  # type: ignore[return-value]

    async def update(self, agent_id: str, updates: dict) -> dict | None:
        existing = await self.get(agent_id)
        if existing is None:
            return None

        db = await get_app_db()
        set_parts: list[str] = []
        params: list = []

        for field in ("name", "role", "description", "device", "accent"):
            if field in updates and updates[field] is not None:
                set_parts.append(f"{field}=?")
                params.append(updates[field])

        if "knowledge" in updates and updates["knowledge"] is not None:
            set_parts.append("knowledge=?")
            params.append(json.dumps(updates["knowledge"], ensure_ascii=False))

        if "online" in updates and updates["online"] is not None:
            set_parts.append("online=?")
            params.append(int(updates["online"]))

        if not set_parts:
            return existing

        params.append(agent_id)
        await db.execute(
            f"UPDATE agent_profiles SET {', '.join(set_parts)} WHERE id=?", params
        )
        await db.commit()

        return await self.get(agent_id)

    async def delete(self, agent_id: str) -> bool:
        db = await get_app_db()
        rows = await db.execute_fetchall(
            "SELECT id FROM agent_profiles WHERE id=?", (agent_id,)
        )
        if not rows:
            return False
        await db.execute("DELETE FROM agent_profiles WHERE id=?", (agent_id,))
        await db.commit()
        return True

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "role": row["role"],
            "device": row["device"],
            "online": bool(row["online"]),
            "description": row["description"],
            "knowledge": json.loads(row["knowledge"]),
            "environment": row["environment"],
            "accent": row["accent"],
            "created_at": row["created_at"],
        }

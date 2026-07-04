from __future__ import annotations

import uuid
from datetime import datetime, timezone

from common.database import get_db


class AutoTaskRepo:

    # ── auto_tasks CRUD ──

    async def create(self, employee_id: str, data: dict) -> dict:
        db = await get_db()
        tid = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO auto_tasks "
            "(id, employee_id, title, description, trigger_type, trigger_config, "
            "instruction, enabled, status, next_run_at, run_count, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                tid,
                employee_id,
                data["title"],
                data.get("description", ""),
                data.get("trigger_type", "manual"),
                data.get("trigger_config", ""),
                data["instruction"],
                int(data.get("enabled", True)),
                "idle",
                data.get("next_run_at"),
                0,
                now,
            ),
        )
        await db.commit()
        return await self.get(tid)  # type: ignore[return-value]

    async def get(self, task_id: str) -> dict | None:
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM auto_tasks WHERE id=?", (task_id,)
        )
        if not rows:
            return None
        return self._row_to_dict(rows[0])

    async def list_by_employee(self, employee_id: str) -> list[dict]:
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM auto_tasks WHERE employee_id=? ORDER BY created_at DESC",
            (employee_id,),
        )
        return [self._row_to_dict(r) for r in rows]

    async def update(self, task_id: str, updates: dict) -> dict | None:
        existing = await self.get(task_id)
        if existing is None:
            return None

        db = await get_db()
        set_parts: list[str] = []
        params: list = []

        for field in (
            "title", "description", "trigger_type", "trigger_config",
            "instruction", "status", "last_run_at", "next_run_at",
        ):
            if field in updates and updates[field] is not None:
                set_parts.append(f"{field}=?")
                params.append(updates[field])

        if "enabled" in updates and updates["enabled"] is not None:
            set_parts.append("enabled=?")
            params.append(int(updates["enabled"]))

        if "run_count" in updates and updates["run_count"] is not None:
            set_parts.append("run_count=?")
            params.append(updates["run_count"])

        if not set_parts:
            return existing

        params.append(task_id)
        await db.execute(
            f"UPDATE auto_tasks SET {', '.join(set_parts)} WHERE id=?", params
        )
        await db.commit()
        return await self.get(task_id)

    async def delete(self, task_id: str) -> bool:
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT id FROM auto_tasks WHERE id=?", (task_id,)
        )
        if not rows:
            return False
        await db.execute("DELETE FROM auto_tasks WHERE id=?", (task_id,))
        await db.commit()
        return True

    async def list_due_tasks(self) -> list[dict]:
        """Find enabled tasks whose next_run_at <= now."""
        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        rows = await db.execute_fetchall(
            "SELECT * FROM auto_tasks "
            "WHERE enabled=1 AND status != 'running' "
            "AND next_run_at IS NOT NULL AND next_run_at <= ?",
            (now,),
        )
        return [self._row_to_dict(r) for r in rows]

    # ── auto_task_runs CRUD ──

    async def create_run(self, auto_task_id: str) -> dict:
        db = await get_db()
        rid = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO auto_task_runs (id, auto_task_id, status, output, started_at) "
            "VALUES (?,?,?,?,?)",
            (rid, auto_task_id, "running", "", now),
        )
        await db.commit()
        return {
            "id": rid,
            "auto_task_id": auto_task_id,
            "status": "running",
            "output": "",
            "started_at": now,
            "finished_at": None,
            "error": None,
        }

    async def finish_run(
        self, run_id: str, status: str, output: str, error: str | None = None
    ) -> dict | None:
        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE auto_task_runs SET status=?, output=?, finished_at=?, error=? WHERE id=?",
            (status, output, now, error, run_id),
        )
        await db.commit()
        rows = await db.execute_fetchall(
            "SELECT * FROM auto_task_runs WHERE id=?", (run_id,)
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "id": r["id"],
            "auto_task_id": r["auto_task_id"],
            "status": r["status"],
            "output": r["output"],
            "started_at": r["started_at"],
            "finished_at": r["finished_at"],
            "error": r["error"],
        }

    async def list_runs(self, auto_task_id: str) -> list[dict]:
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM auto_task_runs WHERE auto_task_id=? ORDER BY started_at DESC",
            (auto_task_id,),
        )
        return [
            {
                "id": r["id"],
                "auto_task_id": r["auto_task_id"],
                "status": r["status"],
                "output": r["output"],
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "error": r["error"],
            }
            for r in rows
        ]

    # ── helpers ──

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row["id"],
            "employee_id": row["employee_id"],
            "title": row["title"],
            "description": row["description"],
            "trigger_type": row["trigger_type"],
            "trigger_config": row["trigger_config"],
            "instruction": row["instruction"],
            "enabled": bool(row["enabled"]),
            "status": row["status"],
            "last_run_at": row["last_run_at"],
            "next_run_at": row["next_run_at"],
            "run_count": row["run_count"],
            "created_at": row["created_at"],
        }

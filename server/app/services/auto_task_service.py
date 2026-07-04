from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from engine.execution.agent_loop import reply as engine_reply

from ..domain.auto_task import AutoTaskCreate, AutoTaskUpdate, AutoTaskOut, AutoTaskRunOut
from ..infrastructure.repositories.auto_task_repo import AutoTaskRepo
from ..infrastructure.repositories.employee_repo import EmployeeRepo
from ..infrastructure.repositories.session_repo import SessionRepo
from ..utils.cron import next_cron_time, next_interval_time

log = logging.getLogger(__name__)


class AutoTaskService:

    def __init__(
        self,
        auto_task_repo: AutoTaskRepo,
        employee_repo: EmployeeRepo,
        session_repo: SessionRepo,
    ) -> None:
        self.repo = auto_task_repo
        self.employee_repo = employee_repo
        self.session_repo = session_repo

    # ── CRUD ──

    async def create_auto_task(
        self, employee_id: str, body: AutoTaskCreate
    ) -> AutoTaskOut:
        emp = await self.employee_repo.get(employee_id)
        if emp is None:
            raise HTTPException(404, "Employee not found")

        next_run = self._calc_next_run(body.trigger_type, body.trigger_config)

        row = await self.repo.create(employee_id, {
            **body.model_dump(),
            "next_run_at": next_run,
        })
        return AutoTaskOut(**row)

    async def list_auto_tasks(self, employee_id: str) -> list[AutoTaskOut]:
        rows = await self.repo.list_by_employee(employee_id)
        return [AutoTaskOut(**r) for r in rows]

    async def get_auto_task(self, task_id: str) -> AutoTaskOut:
        row = await self.repo.get(task_id)
        if row is None:
            raise HTTPException(404, "Auto task not found")
        return AutoTaskOut(**row)

    async def update_auto_task(
        self, task_id: str, body: AutoTaskUpdate
    ) -> AutoTaskOut:
        existing = await self.repo.get(task_id)
        if existing is None:
            raise HTTPException(404, "Auto task not found")

        updates = body.model_dump(exclude_none=True)

        # Recalculate next_run_at if trigger changed
        new_type = updates.get("trigger_type", existing["trigger_type"])
        new_config = updates.get("trigger_config", existing["trigger_config"])
        if "trigger_type" in updates or "trigger_config" in updates:
            updates["next_run_at"] = self._calc_next_run(new_type, new_config)

        row = await self.repo.update(task_id, updates)
        return AutoTaskOut(**row)  # type: ignore[arg-type]

    async def delete_auto_task(self, task_id: str) -> None:
        deleted = await self.repo.delete(task_id)
        if not deleted:
            raise HTTPException(404, "Auto task not found")

    # ── Trigger / Run ──

    async def trigger_auto_task(self, task_id: str) -> AutoTaskRunOut:
        """Manually trigger one run of an auto task."""
        task = await self.repo.get(task_id)
        if task is None:
            raise HTTPException(404, "Auto task not found")
        return await self.run_auto_task(task)

    async def run_auto_task(self, task: dict) -> AutoTaskRunOut:
        """Execute: create a session, send the instruction to engine, save the run."""
        task_id = task["id"]
        employee_id = task["employee_id"]

        # Mark running
        await self.repo.update(task_id, {"status": "running"})
        run = await self.repo.create_run(task_id)

        try:
            emp = await self.employee_repo.get(employee_id)
            emp_name = emp["name"] if emp else "Agent"

            # Create a session for this run
            session = await self.session_repo.create(
                employee_id, f"[自动] {task['title']}"
            )

            # Save the instruction as a user message
            await self.session_repo.add_message(
                session["id"], "user", task["instruction"]
            )

            # Call engine
            reply_text = await engine_reply(
                employee_id, emp_name, task["instruction"]
            )

            # Save the reply
            await self.session_repo.add_message(
                session["id"], "assistant", reply_text
            )

            # Mark completed
            now = datetime.now(timezone.utc).isoformat()
            next_run = self._calc_next_run(
                task["trigger_type"], task["trigger_config"]
            )
            await self.repo.update(task_id, {
                "status": "idle",
                "last_run_at": now,
                "next_run_at": next_run,
                "run_count": task["run_count"] + 1,
            })

            finished = await self.repo.finish_run(
                run["id"], "completed", reply_text
            )
            return AutoTaskRunOut(**finished)  # type: ignore[arg-type]

        except Exception as exc:
            log.exception("Auto task %s failed", task_id)
            now = datetime.now(timezone.utc).isoformat()
            next_run = self._calc_next_run(
                task["trigger_type"], task["trigger_config"]
            )
            await self.repo.update(task_id, {
                "status": "failed",
                "last_run_at": now,
                "next_run_at": next_run,
                "run_count": task["run_count"] + 1,
            })
            finished = await self.repo.finish_run(
                run["id"], "failed", "", error=str(exc)
            )
            return AutoTaskRunOut(**finished)  # type: ignore[arg-type]

    async def list_runs(self, task_id: str) -> list[AutoTaskRunOut]:
        rows = await self.repo.list_runs(task_id)
        return [AutoTaskRunOut(**r) for r in rows]

    # ── Scheduler entry point ──

    async def tick(self) -> int:
        """Called by the scheduler. Run all due tasks. Returns count of tasks run."""
        due = await self.repo.list_due_tasks()
        for task in due:
            try:
                await self.run_auto_task(task)
            except Exception:
                log.exception("Scheduler failed to run task %s", task["id"])
        return len(due)

    # ── helpers ──

    @staticmethod
    def _calc_next_run(
        trigger_type: str, trigger_config: str
    ) -> str | None:
        if trigger_type == "manual":
            return None
        now = datetime.now(timezone.utc)
        try:
            if trigger_type == "cron":
                return next_cron_time(trigger_config, after=now).isoformat()
            if trigger_type == "interval":
                seconds = int(trigger_config)
                return next_interval_time(seconds, after=now).isoformat()
        except (ValueError, TypeError):
            return None
        return None

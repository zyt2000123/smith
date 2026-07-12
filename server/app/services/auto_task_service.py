from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from engine.execution.agent_loop import reply_with_runtime as engine_reply_with_runtime
from engine.execution.runtime import EngineRequest

from ..schemas.auto_task import AutoTaskCreate, AutoTaskUpdate, AutoTaskOut, AutoTaskRunOut
from ..infrastructure.repositories.auto_task_repo import AutoTaskRepo
from ..infrastructure.repositories.agent_profile_repo import AgentProfileRepo
from ..infrastructure.repositories.session_repo import SessionRepo
from .engine_runtime import build_engine_runtime, load_runtime_identity_catalog
from ..utils.cron import next_cron_time, next_interval_time

log = logging.getLogger(__name__)


class AutoTaskService:

    def __init__(
        self,
        auto_task_repo: AutoTaskRepo,
        agent_profile_repo: AgentProfileRepo,
        session_repo: SessionRepo,
    ) -> None:
        self.repo = auto_task_repo
        self.agent_profile_repo = agent_profile_repo
        self.session_repo = session_repo

    # ── CRUD ──

    async def create_auto_task(
        self, agent_id: str, body: AutoTaskCreate
    ) -> AutoTaskOut:
        profile = await self.agent_profile_repo.get(agent_id)
        if profile is None:
            raise HTTPException(404, "Agent profile not found")

        next_run = self._calc_next_run(body.trigger_type, body.trigger_config)

        row = await self.repo.create(agent_id, {
            **body.model_dump(),
            "next_run_at": next_run,
        })
        return AutoTaskOut(**row)

    async def list_auto_tasks(self, agent_id: str) -> list[AutoTaskOut]:
        rows = await self.repo.list_by_agent(agent_id)
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
        result = await self.run_auto_task(task)
        if result is None:
            raise HTTPException(409, "Auto task is already running")
        return result

    async def run_auto_task(self, task: dict) -> AutoTaskRunOut | None:
        """Execute: create a session, send the instruction to engine, save the run."""
        task_id = task["id"]
        agent_id = task["agent_id"]

        if not await self.repo.claim_running(task_id):
            return None

        run = await self.repo.create_run(task_id)
        next_run = self._calc_next_run(task["trigger_type"], task["trigger_config"])

        try:
            profile = await self.agent_profile_repo.get(agent_id)
            profile_name = profile["name"] if profile else "Agent"

            identity_id = load_runtime_identity_catalog().resolve(
                task["instruction"]
            ).identity_id
            session = await self.session_repo.create(
                agent_id,
                f"[自动] {task['title']}",
                identity_id,
            )

            await self.session_repo.add_message(
                session["id"], "user", task["instruction"]
            )

            runtime, services = build_engine_runtime(
                agent_id,
                profile_name,
                session_id=session["id"],
            )
            result = await engine_reply_with_runtime(
                EngineRequest(
                    message=task["instruction"],
                    identity_id=identity_id,
                ),
                runtime,
                services,
            )
            reply_text = result.text

            await self.session_repo.add_message(
                session["id"], "assistant", reply_text
            )

            await self.repo.finish_task(task_id, "idle", next_run)
            finished = await self.repo.finish_run(run["id"], "completed", reply_text)
            if finished is None:
                raise HTTPException(500, "Failed to record auto task run")
            return AutoTaskRunOut(**finished)

        except Exception as exc:
            log.exception("Auto task %s failed", task_id)
            await self.repo.finish_task(task_id, "failed", next_run)
            finished = await self.repo.finish_run(
                run["id"], "failed", "", error=str(exc)
            )
            if finished is None:
                raise HTTPException(500, "Failed to record auto task run") from exc
            return AutoTaskRunOut(**finished)

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
        except (ValueError, TypeError, OverflowError):
            return None
        return None

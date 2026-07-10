"""Background scheduler that ticks every 60 seconds to run due auto tasks."""

from __future__ import annotations

import asyncio
import logging

from .auto_task_service import AutoTaskService
from ..infrastructure.repositories.auto_task_repo import AutoTaskRepo
from ..infrastructure.repositories.agent_profile_repo import AgentProfileRepo
from ..infrastructure.repositories.session_repo import SessionRepo

log = logging.getLogger(__name__)

TICK_INTERVAL = 60  # seconds


def _build_service() -> AutoTaskService:
    return AutoTaskService(AutoTaskRepo(), AgentProfileRepo(), SessionRepo())


async def run_scheduler() -> None:
    """Loop forever, checking for due auto tasks every TICK_INTERVAL seconds."""
    log.info("Scheduler started (tick every %ds)", TICK_INTERVAL)
    while True:
        try:
            svc = _build_service()
            count = await svc.tick()
            if count:
                log.info("Scheduler tick: ran %d auto task(s)", count)
        except asyncio.CancelledError:
            log.info("Scheduler cancelled")
            raise
        except Exception:
            log.exception("Scheduler tick error")
        await asyncio.sleep(TICK_INTERVAL)

from __future__ import annotations

import logging

from fastapi import HTTPException

from common.config import AGENT_DIR
from engine.execution.run_state import RunStateError, RunStateStore

from ..schemas.run import RunStateOut

logger = logging.getLogger(__name__)


class RunStateService:
    """Read-only server adapter for the engine-owned run state store."""

    def __init__(self, store: RunStateStore | None = None) -> None:
        self.store = store

    def get_run(self, agent_id: str, run_id: str) -> RunStateOut:
        store = self.store or RunStateStore(AGENT_DIR)
        try:
            state = store.get(run_id)
        except ValueError:
            raise HTTPException(404, "Run not found")
        except RunStateError:
            logger.warning("unable to read run state (run=%s)", run_id, exc_info=True)
            raise HTTPException(503, "Run state is temporarily unavailable")

        # The API is local-token authenticated, but still enforce the owning
        # agent boundary so a future multi-agent server cannot leak state.
        if state is None or state.agent_id != agent_id:
            raise HTTPException(404, "Run not found")
        return RunStateOut(**state.to_dict())

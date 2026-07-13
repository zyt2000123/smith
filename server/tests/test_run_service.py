from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.run_state_service import RunStateService
from engine.execution.run_state import RunStateStore


def test_run_state_service_only_returns_runs_for_current_agent(tmp_path: Path) -> None:
    store = RunStateStore(tmp_path)
    state = store.create(
        "run-1",
        agent_id="smith-id",
        session_id="session-1",
    )
    service = RunStateService(store)

    result = service.get_run("smith-id", state.run_id)

    assert result.run_id == "run-1"
    assert result.status == "queued"
    assert result.session_id == "session-1"

    with pytest.raises(HTTPException) as exc:
        service.get_run("another-agent", state.run_id)
    assert exc.value.status_code == 404

from __future__ import annotations

import os
from pathlib import Path

import pytest

from engine.execution.run_state import (
    RunStateStore,
    RunStateTransitionError,
    RunStatus,
)


def test_run_state_store_round_trips_and_records_lifecycle(tmp_path: Path) -> None:
    store = RunStateStore(tmp_path)

    state = store.create(
        "run-1",
        agent_id="smith-id",
        session_id="session-1",
        identity_id="smith",
    )

    assert state.status is RunStatus.QUEUED
    store.transition("run-1", RunStatus.RUNNING, event_type="run_started")
    store.record_event("run-1", "tool_call_start", current_tool="shell")
    store.transition("run-1", RunStatus.COMPLETED, event_type="run_finished")

    restored = store.get("run-1")
    assert restored is not None
    assert restored.status is RunStatus.COMPLETED
    assert restored.session_id == "session-1"
    assert restored.identity_id == "smith"
    assert restored.event_seq == 3
    assert restored.last_event_type == "run_finished"
    assert restored.current_tool == "shell"


def test_run_state_rejects_skipping_running_state(tmp_path: Path) -> None:
    store = RunStateStore(tmp_path)
    store.create("run-1", agent_id="smith-id")

    with pytest.raises(RunStateTransitionError):
        store.transition("run-1", RunStatus.COMPLETED)


def test_run_state_store_uses_private_atomic_files(tmp_path: Path) -> None:
    store = RunStateStore(tmp_path)
    store.create("run-1", agent_id="smith-id")

    runs_dir = tmp_path / "runs"
    state_path = runs_dir / "run-1.json"
    assert os.stat(runs_dir).st_mode & 0o777 == 0o700
    assert os.stat(state_path).st_mode & 0o777 == 0o600
    assert not list(runs_dir.glob("*.tmp"))


def test_run_state_store_rejects_path_traversal(tmp_path: Path) -> None:
    store = RunStateStore(tmp_path)

    with pytest.raises(ValueError):
        store.get("../outside")

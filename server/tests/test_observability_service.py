from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.observability_service import ObservabilityService
from engine.observability import (
    EventType,
    ExecutionEvent,
    RunEventRecorder,
    RunMetadata,
    RunSummaryStore,
    TraceStore,
)


def _service_with_run(tmp_path: Path) -> ObservabilityService:
    summaries = RunSummaryStore(tmp_path)
    traces = TraceStore(tmp_path)
    metadata = RunMetadata(
        run_id="run-1",
        agent_id="smith-id",
        session_id="session-1",
        created_at="2026-07-19T00:00:00+00:00",
    )
    recorder = RunEventRecorder(
        "run-1",
        trace_store=traces,
        summary_sinks=(lambda summary: summaries.save(metadata, summary),),
    )
    recorder.record(ExecutionEvent(EventType.TOOL_CALL_START, {"name": "shell"}))
    recorder.record(ExecutionEvent(EventType.TOKEN_USAGE, {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }))
    recorder.record(ExecutionEvent(EventType.RUN_FINISHED, {"status": "completed"}))
    return ObservabilityService(summaries, traces)


def test_observability_service_lists_owned_summaries_and_trace(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)

    runs = service.list_runs("smith-id", limit=10)
    summary = service.get_run("smith-id", "run-1")
    trace = service.get_trace("smith-id", "run-1", limit=10)

    assert [run.run_id for run in runs] == ["run-1"]
    assert summary.outcome == "completed"
    assert summary.tool_call_count == 1
    assert summary.total_tokens == 15
    assert [event.type for event in trace] == ["tool_call_start", "token_usage", "run_finished"]


def test_observability_service_does_not_expose_another_agents_run(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)

    assert service.list_runs("another-agent", limit=10) == []
    with pytest.raises(HTTPException) as exc:
        service.get_trace("another-agent", "run-1", limit=10)
    assert exc.value.status_code == 404

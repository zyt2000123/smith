"""Stable read-side boundary for local Agent observability records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .incidents import IncidentDetector, RunIncident
from .summary_store import RunSummaryRecord, RunSummaryStore
from .trace_store import TraceStore


class ObservabilityReader:
    """Read summaries and bounded trace events without exposing storage layout."""

    def __init__(self, profile_dir: Path) -> None:
        self._summaries = RunSummaryStore(profile_dir)
        self._traces = TraceStore(profile_dir)
        self._incidents = IncidentDetector()

    def list_runs(self, agent_id: str, *, limit: int = 50) -> list[RunSummaryRecord]:
        return self._summaries.list(agent_id, limit=limit)

    def get_run(self, run_id: str) -> RunSummaryRecord | None:
        return self._summaries.get(run_id)

    def read_trace(self, run_id: str, *, limit: int = 300) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        return self._traces.read(run_id)[-limit:]

    def iter_traces(self) -> list[tuple[str, list[dict[str, Any]]]]:
        """Enumerate local traces for aggregate consumers."""
        return self._traces.iter_runs()

    def list_incidents(self, agent_id: str, *, limit: int = 50) -> list[RunIncident]:
        """Return actionable incidents for the agent's most recent completed runs."""
        incidents: list[RunIncident] = []
        for record in self.list_runs(agent_id, limit=limit):
            incidents.extend(self._incidents.detect(record, self._traces.read(record.metadata.run_id)))
        return sorted(incidents, key=lambda incident: incident.occurred_at, reverse=True)[:limit]

from __future__ import annotations

from fastapi import HTTPException

from engine.observability import RunSummaryRecord, RunSummaryStore, TraceStore

from ..schemas.observability import RunSummaryOut, RunTraceEventOut


class ObservabilityService:
    """Read-only, agent-scoped access to local run observability records."""

    def __init__(self, summary_store: RunSummaryStore, trace_store: TraceStore) -> None:
        self.summary_store = summary_store
        self.trace_store = trace_store

    def list_runs(self, agent_id: str, *, limit: int) -> list[RunSummaryOut]:
        return [self._summary_out(record) for record in self.summary_store.list(agent_id, limit=limit)]

    def get_run(self, agent_id: str, run_id: str) -> RunSummaryOut:
        return self._summary_out(self._owned_record(agent_id, run_id))

    def get_trace(self, agent_id: str, run_id: str, *, limit: int) -> list[RunTraceEventOut]:
        self._owned_record(agent_id, run_id)
        try:
            records = self.trace_store.read(run_id)
        except ValueError as exc:
            raise HTTPException(404, "Run not found") from exc
        selected = records[-limit:] if limit else []
        return [RunTraceEventOut(**record) for record in selected]

    def _owned_record(self, agent_id: str, run_id: str) -> RunSummaryRecord:
        try:
            record = self.summary_store.get(run_id)
        except ValueError as exc:
            raise HTTPException(404, "Run not found") from exc
        if record is None or record.metadata.agent_id != agent_id:
            raise HTTPException(404, "Run not found")
        return record

    @staticmethod
    def _summary_out(record: RunSummaryRecord) -> RunSummaryOut:
        usage = record.summary.token_usage
        return RunSummaryOut(
            run_id=record.metadata.run_id,
            agent_id=record.metadata.agent_id,
            session_id=record.metadata.session_id,
            identity_id=record.metadata.identity_id,
            working_dir=record.metadata.working_dir,
            forced_skill=record.metadata.forced_skill,
            created_at=record.metadata.created_at,
            finished_at=record.finished_at,
            outcome=record.summary.outcome,
            reason=record.summary.reason,
            event_count=record.summary.event_count,
            event_counts=dict(record.summary.event_counts),
            tool_call_count=record.summary.tool_call_count,
            backtrack_count=record.summary.backtrack_count,
            approval_required_count=record.summary.approval_required_count,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
        )

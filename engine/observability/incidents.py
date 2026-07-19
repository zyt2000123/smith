"""Deterministic incident detection derived from durable run observability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .summary_store import RunSummaryRecord


@dataclass(frozen=True)
class RunIncident:
    """One actionable signal associated with a completed Agent run."""

    run_id: str
    agent_id: str
    severity: str
    category: str
    message: str
    reason: str | None
    occurred_at: str
    evidence: dict[str, int | str]


class IncidentDetector:
    """Classify common run failures from summaries and redacted trace events."""

    def detect(
        self,
        record: RunSummaryRecord,
        trace: Iterable[dict[str, Any]],
    ) -> list[RunIncident]:
        incidents: list[RunIncident] = []
        summary = record.summary
        base = {
            "run_id": record.metadata.run_id,
            "agent_id": record.metadata.agent_id,
            "occurred_at": record.finished_at,
        }
        reason = summary.reason

        if reason in {"preflight_budget", "tool_failure_budget", "tool_call_budget"}:
            incidents.append(RunIncident(
                **base,
                severity="error",
                category="budget_exhausted",
                message="Run stopped after exhausting its execution budget.",
                reason=reason,
                evidence={"tool_calls": summary.tool_call_count},
            ))
        elif summary.outcome == "failed":
            incidents.append(RunIncident(
                **base,
                severity="error",
                category="run_failed",
                message="Run finished in a failed state.",
                reason=reason,
                evidence={"event_count": summary.event_count},
            ))
        elif summary.outcome in {"cancelled", "incomplete", "blocked"}:
            incidents.append(RunIncident(
                **base,
                severity="warning",
                category=f"run_{summary.outcome}",
                message=f"Run finished as {summary.outcome}.",
                reason=reason,
                evidence={"event_count": summary.event_count},
            ))

        if summary.backtrack_count >= 2:
            incidents.append(RunIncident(
                **base,
                severity="warning",
                category="repeated_backtracks",
                message="Run backtracked repeatedly and may need a routing or skill adjustment.",
                reason=None,
                evidence={"backtrack_count": summary.backtrack_count},
            ))

        timeouts = sum(
            1
            for event in trace
            if event.get("type") == "tool_call_result"
            and isinstance(event.get("data"), dict)
            and _is_timeout(event["data"])
        )
        if timeouts:
            incidents.append(RunIncident(
                **base,
                severity="error",
                category="tool_timeout",
                message="One or more tool calls timed out.",
                reason=None,
                evidence={"timeout_count": timeouts},
            ))
        return incidents


def _is_timeout(data: dict[str, Any]) -> bool:
    status = str(data.get("status") or "").lower()
    reason = str(data.get("reason") or data.get("error") or "").lower()
    return status == "timeout" or "timeout" in reason or "timed out" in reason

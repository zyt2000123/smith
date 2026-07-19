"""Structured, conservative root-cause analysis for one completed run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .incidents import IncidentDetector, RunIncident
from .summary_store import RunSummaryRecord


@dataclass(frozen=True)
class RunDiagnosis:
    """Evidence-backed RCA that proposes changes but never applies them."""

    run_id: str
    agent_id: str
    status: str
    failure_node: str | None
    primary_category: str | None
    summary: str
    evidence: list[str]
    recommendation: str | None


class RunDiagnoser:
    """Translate classified incidents into a stable, human-actionable RCA."""

    def __init__(self, detector: IncidentDetector | None = None) -> None:
        self._detector = detector or IncidentDetector()

    def diagnose(
        self,
        record: RunSummaryRecord,
        trace: Iterable[dict[str, Any]],
    ) -> RunDiagnosis:
        trace_events = list(trace)
        incidents = self._detector.detect(record, trace_events)
        if not incidents:
            return RunDiagnosis(
                run_id=record.metadata.run_id,
                agent_id=record.metadata.agent_id,
                status="healthy",
                failure_node=None,
                primary_category=None,
                summary="No actionable incident was detected for this run.",
                evidence=[],
                recommendation=None,
            )
        primary = _primary_incident(incidents)
        return RunDiagnosis(
            run_id=primary.run_id,
            agent_id=primary.agent_id,
            status="needs_attention",
            failure_node=_failure_node(primary, trace_events),
            primary_category=primary.category,
            summary=primary.message,
            evidence=_evidence(primary, trace_events),
            recommendation=_recommendation(primary),
        )


def _primary_incident(incidents: list[RunIncident]) -> RunIncident:
    priority = {"tool_timeout": 0, "budget_exhausted": 1, "run_failed": 2}
    return min(incidents, key=lambda incident: priority.get(incident.category, 3))


def _failure_node(incident: RunIncident, trace: list[dict[str, Any]]) -> str:
    if incident.category == "tool_timeout":
        for event in trace:
            if event.get("type") != "tool_call_result" or not isinstance(event.get("data"), dict):
                continue
            data = event["data"]
            if str(data.get("status") or "").lower() == "timeout":
                name = data.get("name")
                if isinstance(name, str) and name:
                    return f"tool:{name}"
        return "tool"
    if incident.category == "repeated_backtracks":
        return "routing"
    if incident.category == "budget_exhausted":
        return "execution_budget"
    return "run"


def _evidence(incident: RunIncident, trace: list[dict[str, Any]]) -> list[str]:
    evidence = [f"{key}={value}" for key, value in sorted(incident.evidence.items())]
    if incident.reason:
        evidence.append(f"reason={incident.reason}")
    if incident.category == "tool_timeout":
        names = [
            str(event["data"].get("name"))
            for event in trace
            if event.get("type") == "tool_call_result"
            and isinstance(event.get("data"), dict)
            and event["data"].get("name")
            and str(event["data"].get("status") or "").lower() == "timeout"
        ]
        evidence.extend(f"tool={name}" for name in sorted(set(names)))
    return evidence


def _recommendation(incident: RunIncident) -> str:
    recommendations = {
        "budget_exhausted": "Review the skill plan or tool policy to reduce repeated calls before increasing the budget.",
        "tool_timeout": "Review the affected tool's timeout and retry policy; validate the target before retrying.",
        "repeated_backtracks": "Review routing rules and the skill's exit criteria to avoid cycling between steps.",
        "run_failed": "Inspect the retained trace evidence and address the failing execution dependency before retrying.",
        "run_cancelled": "Resume only when the user still expects the incomplete work to continue.",
        "run_incomplete": "Review the terminal reason and resume the run only if its prerequisites are still valid.",
        "run_blocked": "Resolve the blocking approval or prerequisite, then retry through the normal approval gate.",
    }
    return recommendations[incident.category]

"""Local-first execution observability primitives.

This package owns the durable, append-only record of an Agent run and the
small projections derived from it.  Execution code emits events and records
them through :class:`RunEventRecorder`; it does not need to know how traces
are stored or how summaries are calculated.
"""

from .events import EventType, ExecutionEvent, raw_text_delta
from .projections import RunSummary, RunSummaryProjection
from .recorder import RunEventRecorder
from .trace_store import TraceStore

__all__ = (
    "EventType",
    "ExecutionEvent",
    "RunEventRecorder",
    "RunSummary",
    "RunSummaryProjection",
    "TraceStore",
    "raw_text_delta",
)

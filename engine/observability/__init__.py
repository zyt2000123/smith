"""Local-first execution observability primitives.

This package owns the durable, append-only record of an Agent run, its
aggregate projections, and all supported read access. Execution code uses
``RunObservation``; service code uses ``ObservabilityReader``. Neither needs
to know the trace or summary storage layout.
"""

from .events import EventType, ExecutionEvent, raw_text_delta
from .incidents import IncidentDetector, RunIncident
from .projections import RunSummary, RunSummaryProjection
from .recorder import RunEventRecorder
from .reader import ObservabilityReader
from .runtime import RunObservation, RunObservationContext
from .summary_store import RunMetadata, RunSummaryRecord, RunSummaryStore
from .trace_store import TraceStore

__all__ = (
    "EventType",
    "ExecutionEvent",
    "IncidentDetector",
    "RunEventRecorder",
    "RunIncident",
    "RunObservation",
    "RunObservationContext",
    "RunMetadata",
    "RunSummary",
    "RunSummaryRecord",
    "RunSummaryProjection",
    "RunSummaryStore",
    "TraceStore",
    "ObservabilityReader",
    "raw_text_delta",
)

"""Compatibility exports for the execution event contract.

The canonical observability event contract now lives in
``engine.observability.events``.  This import path remains during migration
for integrations that imported execution events directly.
"""

from engine.observability.events import EventType, ExecutionEvent, raw_text_delta

__all__ = ("EventType", "ExecutionEvent", "raw_text_delta")

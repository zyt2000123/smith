"""Compatibility export for the trace store.

The canonical store lives in ``engine.observability.trace_store``.  This
module stays import-compatible while consumers migrate to the observability
boundary.
"""

from engine.observability.trace_store import TraceStore

__all__ = ("TraceStore",)

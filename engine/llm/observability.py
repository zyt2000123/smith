"""Generation-level observability for every LLM call.

``ProviderClient`` emits one :class:`GenerationRecord` per model call —
main-loop and side-channel alike (compaction, memory compilation, routing,
gate review).  Callers attribute usage with :func:`llm_purpose`, run scope
with :func:`generation_context`, and consumers install a sink either for a
scope (:func:`generation_sink`) or process-wide
(:func:`set_default_generation_sink`).

Recording is strictly best-effort: a missing or failing sink never affects
the model call itself.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger(__name__)

GenerationSink = Callable[["GenerationRecord"], Awaitable[None]]

_purpose: ContextVar[str] = ContextVar("llm_generation_purpose", default="other")
_scope: ContextVar[tuple[str | None, str | None]] = ContextVar(
    "llm_generation_scope", default=(None, None)
)
_sink: ContextVar[GenerationSink | None] = ContextVar("llm_generation_sink", default=None)
_default_sink: GenerationSink | None = None


@dataclass(frozen=True)
class GenerationRecord:
    """The normalized accounting record of one model call."""

    provider: str
    model: str
    purpose: str
    usage: dict[str, int]
    ttft_ms: int | None
    total_ms: int
    stream: bool
    ok: bool
    run_id: str | None = None
    session_id: str | None = None
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_key: str = field(default_factory=lambda: uuid4().hex)


@contextmanager
def llm_purpose(label: str) -> Iterator[None]:
    """Attribute LLM calls in this scope to one purpose label."""
    token = _purpose.set(label)
    try:
        yield
    finally:
        _purpose.reset(token)


@contextmanager
def generation_context(
    run_id: str | None = None,
    session_id: str | None = None,
) -> Iterator[None]:
    """Attribute LLM calls in this scope to one run/session."""
    token = _scope.set((run_id, session_id))
    try:
        yield
    finally:
        _scope.reset(token)


@contextmanager
def generation_sink(sink: GenerationSink) -> Iterator[None]:
    """Route generation records in this scope to ``sink``."""
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


def set_default_generation_sink(sink: GenerationSink | None) -> None:
    """Install the process-wide fallback sink (platform startup owns this)."""
    global _default_sink
    _default_sink = sink


def current_purpose() -> str:
    return _purpose.get()


def current_generation_scope() -> tuple[str | None, str | None]:
    return _scope.get()


async def emit_generation(record: GenerationRecord) -> None:
    """Deliver one record to the active sink without leaking failures."""
    sink = _sink.get() or _default_sink
    if sink is None:
        return
    try:
        await sink(record)
    except Exception:
        logger.warning(
            "failed to record llm generation (purpose=%s, model=%s)",
            record.purpose,
            record.model,
            exc_info=True,
        )

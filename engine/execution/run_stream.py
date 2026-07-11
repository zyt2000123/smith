"""A small, typed run-stream result inspired by the Agents SDK contract."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import AsyncGenerator

from .events import EventType, ExecutionEvent


class AgentRunStream:
    """Own one agent run's event iterator and expose its terminal state.

    Consumers must drain :meth:`stream_events` before relying on
    ``is_complete``.  This mirrors the important Agents SDK rule that the
    final visible text token is not necessarily the end of the run: persistence
    and service cleanup may still be running.
    """

    def __init__(self, run_id: str, events: AsyncIterator[ExecutionEvent]) -> None:
        self.run_id = run_id
        self._events = events
        self._consumed = False
        self.is_complete = False
        self.status: str | None = None
        self.reason: str | None = None

    async def stream_events(self) -> AsyncGenerator[ExecutionEvent, None]:
        """Yield the run events once, updating terminal state on completion."""
        if self._consumed:
            raise RuntimeError("AgentRunStream events can only be consumed once.")
        self._consumed = True

        async for event in self._events:
            if event.type == EventType.RUN_FINISHED:
                status = event.data.get("status")
                reason = event.data.get("reason")
                self.status = status if isinstance(status, str) else "failed"
                self.reason = reason if isinstance(reason, str) else None
                self.is_complete = True
            yield event

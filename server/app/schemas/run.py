from __future__ import annotations

from pydantic import BaseModel


class RunStateOut(BaseModel):
    run_id: str
    agent_id: str
    session_id: str | None = None
    identity_id: str | None = None
    status: str
    created_at: str
    updated_at: str
    event_seq: int
    last_event_type: str | None = None
    current_skill: str | None = None
    current_tool: str | None = None
    reason: str | None = None
    error: str | None = None

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunSummaryOut(BaseModel):
    run_id: str
    agent_id: str
    session_id: str | None = None
    identity_id: str | None = None
    working_dir: str | None = None
    forced_skill: str | None = None
    created_at: str
    finished_at: str
    outcome: str | None = None
    reason: str | None = None
    event_count: int = Field(ge=0)
    event_counts: dict[str, int]
    tool_call_count: int = Field(ge=0)
    backtrack_count: int = Field(ge=0)
    approval_required_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class RunTraceEventOut(BaseModel):
    seq: int = Field(ge=1)
    timestamp: str
    run_id: str
    type: str
    data: dict[str, Any]

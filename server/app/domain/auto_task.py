from __future__ import annotations

from pydantic import BaseModel


class AutoTaskCreate(BaseModel):
    title: str
    description: str = ""
    trigger_type: str = "manual"  # "manual" | "cron" | "interval"
    trigger_config: str = ""  # cron expression or interval seconds
    instruction: str  # the task instruction to send to the agent
    enabled: bool = True


class AutoTaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    trigger_type: str | None = None
    trigger_config: str | None = None
    instruction: str | None = None
    enabled: bool | None = None


class AutoTaskOut(BaseModel):
    id: str
    employee_id: str
    title: str
    description: str
    trigger_type: str
    trigger_config: str
    instruction: str
    enabled: bool
    status: str  # "idle" | "running" | "completed" | "failed"
    last_run_at: str | None
    next_run_at: str | None
    run_count: int
    created_at: str


class AutoTaskRunOut(BaseModel):
    id: str
    auto_task_id: str
    status: str  # "running" | "completed" | "failed"
    output: str
    started_at: str
    finished_at: str | None
    error: str | None

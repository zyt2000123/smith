from typing import Literal

from pydantic import BaseModel


class TaskCreate(BaseModel):
    type: Literal["conversation", "automation"] = "conversation"
    title: str = ""


class TaskOut(BaseModel):
    id: str
    agent_id: str
    type: str
    title: str
    status: str
    session_id: str | None = None
    created_at: str
    updated_at: str

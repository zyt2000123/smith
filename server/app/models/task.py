from pydantic import BaseModel

class TaskCreate(BaseModel):
    type: str = "conversation"
    title: str = ""

class TaskOut(BaseModel):
    id: str
    employee_id: str
    type: str
    title: str
    status: str
    session_id: str | None
    created_at: str
    updated_at: str

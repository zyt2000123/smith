from pydantic import BaseModel


class SessionCreate(BaseModel):
    title: str = ""


class SessionOut(BaseModel):
    id: str
    employee_id: str
    title: str
    created_at: str
    last_message_preview: str | None = None
    last_message_at: str | None = None
    message_count: int = 0


class MessageCreate(BaseModel):
    content: str


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str

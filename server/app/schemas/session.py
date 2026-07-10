from pydantic import BaseModel


class SessionCreate(BaseModel):
    title: str = "新对话"


class SessionOut(BaseModel):
    id: str
    agent_id: str
    title: str
    created_at: str
    last_message_preview: str | None = None
    last_message_at: str | None = None
    message_count: int = 0


class MessageCreate(BaseModel):
    content: str
    context: str | None = None
    skill_name: str | None = None


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str

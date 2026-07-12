from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str = "新对话"
    identity_id: str | None = None


class SessionOut(BaseModel):
    id: str
    agent_id: str
    identity_id: str | None = None
    title: str
    created_at: str
    last_message_preview: str | None = None
    last_message_at: str | None = None
    message_count: int = 0


class MessageCreate(BaseModel):
    content: str = Field(max_length=100_000)
    context: str | None = Field(default=None, max_length=50_000)
    skill_name: str | None = None
    identity_id: str | None = None
    working_dir: str | None = None


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str

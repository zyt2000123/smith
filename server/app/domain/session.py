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
    # 隐式环境上下文（工作目录/附件路径等）：只注入引擎，不落库、不显示
    context: str | None = None
    # 显式 skill 选择：仅本轮生效，优先于自动路由
    skill_name: str | None = None


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str

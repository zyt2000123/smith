from pydantic import BaseModel

class SessionCreate(BaseModel):
    title: str = ""

class SessionOut(BaseModel):
    id: str
    employee_id: str
    title: str
    created_at: str

class MessageCreate(BaseModel):
    content: str

class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str

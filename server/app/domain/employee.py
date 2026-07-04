from pydantic import BaseModel, Field


class EmployeeCreate(BaseModel):
    name: str
    role: str
    description: str = ""
    device: str = ""
    knowledge: list[str] = Field(default_factory=list)
    environment: str = "本地"
    accent: str = ""


class EmployeeUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    description: str | None = None
    device: str | None = None
    knowledge: list[str] | None = None
    online: bool | None = None
    accent: str | None = None


class EmployeeOut(BaseModel):
    id: str
    name: str
    role: str
    device: str
    online: bool
    description: str
    knowledge: list[str]
    environment: str
    accent: str
    created_at: str

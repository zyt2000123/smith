from pydantic import BaseModel, Field


class TeamGroupCreate(BaseModel):
    name: str
    description: str = ""
    member_ids: list[str] = Field(default_factory=list)


class TeamGroupOut(BaseModel):
    id: str
    name: str
    description: str
    member_ids: list[str]
    created_at: str


class TeamMessageCreate(BaseModel):
    content: str


class TeamMessageOut(BaseModel):
    id: str
    group_id: str
    sender_id: str
    sender_name: str
    content: str
    mentions: list[str]
    created_at: str

from pydantic import BaseModel, Field


class ProjectInstructionInit(BaseModel):
    working_dir: str = Field(min_length=1, max_length=4096)


class ProjectInstructionOut(BaseModel):
    path: str
    created: bool

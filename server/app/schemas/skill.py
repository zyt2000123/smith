from pydantic import BaseModel


class SkillSummaryOut(BaseModel):
    name: str
    description: str
    source: str
    version: str
    argument_hint: str = ""

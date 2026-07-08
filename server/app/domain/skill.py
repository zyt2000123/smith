from pydantic import BaseModel


class SkillSummaryOut(BaseModel):
    name: str
    description: str = ""
    source: str
    version: str = "0.1.0"
    argument_hint: str = ""

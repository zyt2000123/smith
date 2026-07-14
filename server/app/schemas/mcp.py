from pydantic import BaseModel, ConfigDict, Field


class McpToolSummaryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str = ""
    input_schema: dict = Field(default_factory=dict, alias="inputSchema")


class McpServerOut(BaseModel):
    name: str
    type: str
    url: str | None = None
    command: list[str] = Field(default_factory=list)
    status: str
    error: str | None = None
    tools: list[McpToolSummaryOut] = Field(default_factory=list)

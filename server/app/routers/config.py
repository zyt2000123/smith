import os
from fastapi import APIRouter
from pydantic import BaseModel
from ..agent_runtime import _agents

router = APIRouter(prefix="/api/config", tags=["config"])

class LLMConfig(BaseModel):
    api_key: str
    base_url: str | None = None
    model: str = "gpt-4o-mini"

@router.post("/llm")
async def set_llm_config(body: LLMConfig):
    """Set LLM config at runtime (env vars). Clears cached agents to pick up new config."""
    os.environ["AGENTSMITH_LLM_API_KEY"] = body.api_key
    if body.base_url:
        os.environ["AGENTSMITH_LLM_BASE_URL"] = body.base_url
    os.environ["AGENTSMITH_LLM_MODEL"] = body.model
    _agents.clear()
    return {"status": "ok", "model": body.model}

@router.get("/llm")
async def get_llm_config():
    key = os.environ.get("AGENTSMITH_LLM_API_KEY", "")
    return {
        "configured": bool(key),
        "model": os.environ.get("AGENTSMITH_LLM_MODEL", "gpt-4o-mini"),
        "base_url": os.environ.get("AGENTSMITH_LLM_BASE_URL", ""),
    }

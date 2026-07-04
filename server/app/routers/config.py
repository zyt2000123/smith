from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..services.config_service import ConfigService

router = APIRouter(prefix="/api/config", tags=["config"])


class LLMConfig(BaseModel):
    api_key: str
    base_url: str | None = None
    model: str = "gpt-4o-mini"


def get_config_service() -> ConfigService:
    return ConfigService()


@router.get("/llm")
async def get_llm_config(svc: ConfigService = Depends(get_config_service)):
    return svc.get_llm_config()


@router.post("/llm")
async def set_llm_config(body: LLMConfig, svc: ConfigService = Depends(get_config_service)):
    return svc.set_llm_config(body.api_key, body.base_url, body.model)

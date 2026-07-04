from fastapi import APIRouter
from ..templates.roles import ROLE_TEMPLATES

router = APIRouter(prefix="/api/templates", tags=["templates"])

@router.get("")
async def list_templates():
    return ROLE_TEMPLATES

from fastapi import APIRouter, Depends

from ..services.template_service import TemplateService

router = APIRouter(
    prefix="/api/templates",
    tags=["legacy-templates"],
    include_in_schema=False,
)


def get_template_service() -> TemplateService:
    return TemplateService()


@router.get("")
async def list_templates(svc: TemplateService = Depends(get_template_service)):
    return await svc.list_templates()

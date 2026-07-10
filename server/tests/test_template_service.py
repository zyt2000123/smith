from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import SMITH_PROFILE_DIR  # noqa: E402
from engine.llm.model_config import SMITH_TEMPLATE_ID  # noqa: E402
from app.services.template_service import TemplateService  # noqa: E402


@pytest.mark.asyncio
async def test_list_templates_exposes_only_builtin_smith_identity() -> None:
    templates = await TemplateService().list_templates()

    assert SMITH_PROFILE_DIR.name == "smith"
    assert (SMITH_PROFILE_DIR / "role.md").is_file()
    assert templates
    assert [template["id"] for template in templates] == [SMITH_TEMPLATE_ID]

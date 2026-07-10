from __future__ import annotations

from common.config import LEGACY_AGENT_PROFILES_DIR, PATHS, SAFETY_RULES_PATH
from engine.execution.runtime import RuntimeContext, RuntimeServices
from engine.llm.model_config import build_llm_client, resolve_llm_config
from engine.safety.tool_guard import ToolGuard
from engine.skill.registry import SkillRegistry
from engine.tool.registry import ToolRegistry


def build_engine_runtime(
    agent_id: str,
    agent_name: str,
    *,
    session_id: str | None = None,
) -> tuple[RuntimeContext, RuntimeServices]:
    """Build the engine runtime for the FastAPI product layer."""
    runtime = RuntimeContext(
        agent_id=agent_id,
        agent_name=agent_name,
        profile_dir=LEGACY_AGENT_PROFILES_DIR / agent_id,
        agents_dir=PATHS.project_root / "agents",
        session_id=session_id,
    )
    services = RuntimeServices(
        llm=build_llm_client(resolve_llm_config(agent_id)),
        tool_registry=ToolRegistry(),
        skill_registry=SkillRegistry(),
        tool_guard=ToolGuard(SAFETY_RULES_PATH),
    )
    return runtime, services

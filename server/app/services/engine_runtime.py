from __future__ import annotations

from common.config import AGENT_DIR, BUILTIN_IDENTITIES_DIR, PATHS, SAFETY_RULES_PATH
from engine.execution.skill_chain import SkillChain, load_gate_content
from engine.identity_catalog import IdentityCatalog, load_identity_catalog
from engine.execution.runtime import RuntimeContext, RuntimeServices
from engine.llm.model_config import LLMUsage, build_llm_client, resolve_llm_config
from engine.safety.tool_guard import ToolGuard
from engine.skill.registry import SkillRegistry
from engine.tool.registry import ToolRegistry


def load_runtime_identity_catalog(*, force: bool = False) -> IdentityCatalog:
    """Load the one catalog and validate its declared assets for every entry point."""
    catalog = load_identity_catalog(BUILTIN_IDENTITIES_DIR, force=force)
    # 门禁/条件内容必须先于 pipeline YAML 解析注册，否则合法 gate key 报 unknown。
    load_gate_content(PATHS.project_root / "agents")
    pipelines = SkillChain.load_pipelines(PATHS.project_root / "agents" / "pipelines")
    skill_registry = SkillRegistry()
    skill_registry.load_builtin(PATHS.project_root / "agents" / "skills")
    skill_registry.load_agent_skills(AGENT_DIR / "skills")
    catalog.validate_assets(
        pipelines.keys(),
        (summary["name"] for summary in skill_registry.list_summaries()),
    )
    return catalog


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
        profile_dir=AGENT_DIR,
        agents_dir=PATHS.project_root / "agents",
        session_id=session_id,
        identity_catalog=load_runtime_identity_catalog(),
    )
    interactive_config = resolve_llm_config(usage=LLMUsage.INTERACTIVE)
    gate_config = resolve_llm_config(usage=LLMUsage.GATE)
    services = RuntimeServices(
        llm=build_llm_client(interactive_config),
        gate_llm=build_llm_client(gate_config),
        tool_registry=ToolRegistry(),
        skill_registry=SkillRegistry(),
        tool_guard=ToolGuard(SAFETY_RULES_PATH),
    )
    return runtime, services

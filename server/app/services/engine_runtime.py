from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any

from common.config import AGENT_DIR, BUILTIN_IDENTITIES_DIR, PATHS, SAFETY_RULES_PATH
from engine.execution.skill_chain import SkillChain, load_gate_content
from engine.identity_catalog import IdentityCatalog, load_identity_catalog
from engine.execution.runtime import RuntimeContext, RuntimeServices
from engine.llm.model_config import LLMUsage, build_llm_client, resolve_llm_config
from engine.llm.contracts import GEMINI_OPENAI_BASE_URL
from engine.llm.factory import normalize_provider_name
from engine.llm.port import LLMPort
from engine.safety.tool_guard import ToolGuard
from engine.skill.registry import SkillRegistry
from engine.tool.registry import ToolRegistry


def _config_fingerprint(config: dict[str, Any]) -> str:
    """Stable cache key for a fully resolved LLM route."""
    return json.dumps(_normalize_llm_config(config), sort_keys=True, separators=(",", ":"), default=str)


def _normalize_llm_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize equivalent LLM configs before cache lookup."""
    normalized = dict(config)
    provider = normalize_provider_name(normalized.get("provider", ""))
    normalized["provider"] = provider
    if provider == "gemini" and not str(normalized.get("base_url") or "").strip():
        normalized["base_url"] = GEMINI_OPENAI_BASE_URL
    return normalized


@dataclass
class LLMClientManager:
    """Factory/cache for process-scoped LLM clients."""

    _clients: dict[str, LLMPort] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def get(self, usage: LLMUsage) -> LLMPort:
        config = resolve_llm_config(usage=usage)
        return self.get_for_config(config)

    def get_for_config(self, config: dict[str, Any]) -> LLMPort:
        fingerprint = _config_fingerprint(config)
        with self._lock:
            client = self._clients.get(fingerprint)
            if client is None:
                client = build_llm_client(config)
                self._clients[fingerprint] = client
            return client

    async def close(self) -> None:
        with self._lock:
            clients = list({id(client): client for client in self._clients.values()}.values())
            self._clients.clear()
        for client in clients:
            await client.close()


_llm_client_manager = LLMClientManager()


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
    llm_client_manager: LLMClientManager | None = None,
) -> tuple[RuntimeContext, RuntimeServices]:
    """Build the engine runtime for the FastAPI product layer."""
    manager = llm_client_manager or _llm_client_manager
    runtime = RuntimeContext(
        agent_id=agent_id,
        agent_name=agent_name,
        profile_dir=AGENT_DIR,
        agents_dir=PATHS.project_root / "agents",
        session_id=session_id,
        identity_catalog=load_runtime_identity_catalog(),
    )
    services = RuntimeServices(
        llm=manager.get(LLMUsage.INTERACTIVE),
        gate_llm=manager.get(LLMUsage.GATE),
        tool_registry=ToolRegistry(),
        skill_registry=SkillRegistry(),
        tool_guard=ToolGuard(SAFETY_RULES_PATH),
        owns_llm_clients=False,
    )
    return runtime, services


async def close_shared_llm_clients() -> None:
    """Close process-scoped LLM clients during server shutdown."""
    await _llm_client_manager.close()

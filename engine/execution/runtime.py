from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from engine.identity_catalog import IdentityCatalog
from engine.llm.port import LLMPort
from engine.safety.tool_guard import ToolGuard
from engine.skill.registry import SkillRegistry
from engine.tool.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EngineRequest:
    """A single user request submitted to the engine."""

    message: str
    history: list[dict] | None = None
    context: str | None = None
    forced_skill: str | None = None
    identity_id: str | None = None
    working_dir: str | None = None


@dataclass(frozen=True)
class RuntimeContext:
    """Runtime identity and filesystem context already resolved by the caller."""

    agent_id: str
    agent_name: str
    profile_dir: Path
    agents_dir: Path
    session_id: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)
    identity_catalog: IdentityCatalog | None = None


@dataclass
class RuntimeServices:
    """Per-request services owned by the caller and consumed by the engine."""

    llm: LLMPort
    tool_registry: ToolRegistry
    skill_registry: SkillRegistry
    gate_llm: LLMPort | None = None
    tool_guard: ToolGuard | None = None
    mcp_clients: list[Any] = field(default_factory=list)

    async def close(self) -> None:
        # 逐资源隔离：第一个 close 抛异常不许掐断其余资源的清理，
        # 否则 MCP 子进程/LLM 连接会在长期运行的进程里泄漏。
        for client in reversed(self.mcp_clients):
            try:
                close = getattr(client, "close", None)
                if close is None:
                    continue
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.warning(
                    "failed to close MCP client %s", type(client).__name__, exc_info=True,
                )

        closed_llms: set[int] = set()
        for llm in (self.gate_llm, self.llm):
            if llm is None or id(llm) in closed_llms:
                continue
            closed_llms.add(id(llm))
            try:
                close_llm = getattr(llm, "close", None)
                if close_llm is None:
                    continue
                result = close_llm()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.warning(
                    "failed to close LLM client %s", type(llm).__name__, exc_info=True,
                )


@dataclass(frozen=True)
class EngineResult:
    text: str
    had_tools: bool = False

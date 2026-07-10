from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class BuiltInAgentSpec:
    key: str
    name: str
    role: str
    description: str
    aliases: tuple[str, ...]


BUILTIN_AGENT = BuiltInAgentSpec(
    key="assistant",
    name="Smith",
    role="personal-assistant",
    description=(
        "面向个人工作流的常驻本地 Agent，负责理解目标、整理上下文、检索信息、"
        "规划执行并交付可落地结果。"
    ),
    aliases=("smith", "assistant", "agent", "default", "pa", "personal-assistant"),
)

SHELL_ALIASES = {"shell", "ui"}


class AgentProfileServiceLike(Protocol):
    async def list_profiles(self) -> list[Any]:
        ...

    async def create_profile(self, body: Any) -> Any:
        ...


class SessionServiceLike(Protocol):
    async def list_sessions(self, agent_id: str) -> list[Any]:
        ...

    async def create_session(self, agent_id: str, title: str) -> Any:
        ...

    async def list_messages(
        self,
        session_id: str,
        limit: int = 0,
        offset: int = 0,
    ) -> list[Any]:
        ...


def _normalize(value: str) -> str:
    return value.strip().lower()


def _find_builtin_agent_spec(selector: str) -> BuiltInAgentSpec | None:
    key = _normalize(selector)
    if key == BUILTIN_AGENT.key or key in BUILTIN_AGENT.aliases:
        return BUILTIN_AGENT
    return None

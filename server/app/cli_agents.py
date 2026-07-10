from __future__ import annotations

from typing import Any, Sequence

from common.config import SMITH_PROFILE_DIR

from .cli_identity import (
    BUILTIN_AGENT,
    AgentProfileServiceLike,
    SessionServiceLike,
    _find_builtin_agent_spec,
    _normalize,
)


async def _build_agent_profile_service() -> Any:
    from .infrastructure.repositories.agent_profile_repo import AgentProfileRepo
    from .services.agent_profile_service import AgentProfileService

    return AgentProfileService(AgentProfileRepo())


async def _build_session_service() -> Any:
    from .infrastructure.repositories.agent_profile_repo import AgentProfileRepo
    from .infrastructure.repositories.session_repo import SessionRepo
    from .services.session_service import SessionService

    return SessionService(SessionRepo(), AgentProfileRepo())


async def ensure_builtin_agent(agent_profile_service: AgentProfileServiceLike) -> Any:
    from .schemas.agent_profile import AgentProfileCreate

    existing = await agent_profile_service.list_profiles()
    by_name_role = {
        (_normalize(agent.name), _normalize(agent.role)): agent
        for agent in existing
    }

    spec = BUILTIN_AGENT
    match = by_name_role.get((_normalize(spec.name), _normalize(spec.role)))
    if match is not None:
        return match

    if not SMITH_PROFILE_DIR.is_dir():
        raise RuntimeError("Missing built-in Smith profile directory.")

    return await agent_profile_service.create_profile(
        AgentProfileCreate(
            name=spec.name,
            role=spec.role,
            description=spec.description,
        )
    )


async def ensure_demo_agents(agent_profile_service: AgentProfileServiceLike) -> list[Any]:
    return [await ensure_builtin_agent(agent_profile_service)]


def _match_agent_from_list(selector: str, agents: Sequence[Any]) -> Any | None:
    key = _normalize(selector)
    spec = _find_builtin_agent_spec(selector)

    if spec is not None:
        for agent in agents:
            if (
                _normalize(agent.name) == _normalize(spec.name)
                and _normalize(agent.role) == _normalize(spec.role)
            ):
                return agent

    exact_matches = [
        agent
        for agent in agents
        if key in {
            _normalize(agent.id),
            _normalize(agent.name),
            _normalize(agent.role),
        }
    ]
    if exact_matches:
        return exact_matches[0]

    if spec is None:
        return None

    for agent in agents:
        if (
            _normalize(agent.name) == _normalize(spec.name)
            or _normalize(agent.role) == _normalize(spec.role)
        ):
            return agent
    return None


async def resolve_agent(
    agent_profile_service: AgentProfileServiceLike,
    selector: str,
    *,
    ensure_builtin: bool,
) -> Any:
    if ensure_builtin:
        await ensure_builtin_agent(agent_profile_service)
    agents = await agent_profile_service.list_profiles()
    agent = _match_agent_from_list(selector, agents)
    if agent is None:
        raise RuntimeError(
            f"Agent `{selector}` not found. Run `agent ensure` or `agent show` first."
        )
    return agent


def _find_session_in_list(session_id: str, sessions: Sequence[Any]) -> Any | None:
    key = _normalize(session_id)
    for session in sessions:
        if _normalize(getattr(session, "id", "")) == key:
            return session
    return None


async def resolve_session(
    session_service: SessionServiceLike,
    agent: Any,
    session_id: str,
) -> Any:
    sessions = await session_service.list_sessions(agent.id)
    session = _find_session_in_list(session_id, sessions)
    if session is None:
        raise RuntimeError(
            f"Session `{session_id}` not found for agent `{agent.name}`."
        )
    return session

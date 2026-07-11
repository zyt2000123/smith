from __future__ import annotations

from typing import Any, Sequence


async def _build_agent_service() -> Any:
    from .services.agent_service import AgentService

    return AgentService()


async def ensure_smith(agent_service: Any) -> Any:
    """Return the one resident Smith profile, creating it when needed."""
    return await agent_service.get_profile()


def _find_session_in_list(session_id: str, sessions: Sequence[Any]) -> Any | None:
    key = session_id.strip().lower()
    for session in sessions:
        if str(getattr(session, "id", "")).strip().lower() == key:
            return session
    return None


async def resolve_session(agent_service: Any, session_id: str) -> Any:
    session = _find_session_in_list(session_id, await agent_service.list_sessions())
    if session is None:
        raise RuntimeError(f"Session `{session_id}` not found for Smith.")
    return session

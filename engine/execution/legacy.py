from __future__ import annotations

from typing import AsyncGenerator

from common.config import LEGACY_AGENT_PROFILES_DIR, PATHS, SAFETY_RULES_PATH
from engine.execution.events import ExecutionEvent
from engine.execution.runtime import EngineRequest, RuntimeContext, RuntimeServices
from engine.llm.model_config import build_llm_client, resolve_llm_config
from engine.safety.tool_guard import ToolGuard
from engine.skill.registry import SkillRegistry
from engine.tool.registry import ToolRegistry


def _legacy_runtime(
    agent_id: str,
    name: str,
    session_id: str | None = None,
) -> tuple[RuntimeContext, RuntimeServices]:
    runtime = RuntimeContext(
        agent_id=agent_id,
        agent_name=name,
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


async def reply(
    agent_id: str,
    name: str,
    user_message: str,
    history: list[dict] | None = None,
    context: str | None = None,
    forced_skill: str | None = None,
) -> str:
    from engine.execution.agent_loop import reply_with_runtime

    runtime, services = _legacy_runtime(agent_id, name)
    result = await reply_with_runtime(
        EngineRequest(
            message=user_message,
            history=history,
            context=context,
            forced_skill=forced_skill,
        ),
        runtime,
        services,
    )
    return result.text


async def reply_events(
    agent_id: str,
    name: str,
    user_message: str,
    history: list[dict] | None = None,
    context: str | None = None,
    forced_skill: str | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[ExecutionEvent, None]:
    from engine.execution.agent_loop import reply_events_with_runtime

    runtime, services = _legacy_runtime(agent_id, name, session_id=session_id)
    async for event in reply_events_with_runtime(
        EngineRequest(
            message=user_message,
            history=history,
            context=context,
            forced_skill=forced_skill,
        ),
        runtime,
        services,
    ):
        yield event


async def reply_stream(
    agent_id: str,
    name: str,
    user_message: str,
    history: list[dict] | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    from engine.execution.agent_loop import reply_stream_with_runtime

    runtime, services = _legacy_runtime(agent_id, name, session_id=session_id)
    async for chunk in reply_stream_with_runtime(
        EngineRequest(message=user_message, history=history),
        runtime,
        services,
    ):
        yield chunk

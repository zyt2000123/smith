from __future__ import annotations

from typing import AsyncGenerator

from common.config import AGENT_PROFILES_DIR, PATHS, SAFETY_RULES_PATH
from common.config_loader import resolve_llm_config
from engine.execution.events import ExecutionEvent
from engine.execution.runtime import EngineRequest, RuntimeContext, RuntimeServices
from engine.llm.model_config import build_llm_client
from engine.safety.tool_guard import ToolGuard
from engine.skill.registry import SkillRegistry
from engine.tool.registry import ToolRegistry


def _legacy_runtime(
    employee_id: str,
    name: str,
    session_id: str | None = None,
) -> tuple[RuntimeContext, RuntimeServices]:
    runtime = RuntimeContext(
        agent_id=employee_id,
        agent_name=name,
        profile_dir=AGENT_PROFILES_DIR / employee_id,
        agents_dir=PATHS.project_root / "agents",
        session_id=session_id,
    )
    services = RuntimeServices(
        llm=build_llm_client(resolve_llm_config(employee_id)),
        tool_registry=ToolRegistry(),
        skill_registry=SkillRegistry(),
        tool_guard=ToolGuard(SAFETY_RULES_PATH),
    )
    return runtime, services


async def reply(
    employee_id: str,
    name: str,
    user_message: str,
    history: list[dict] | None = None,
    context: str | None = None,
    forced_skill: str | None = None,
) -> str:
    from engine.execution.agent_loop import reply_with_runtime

    runtime, services = _legacy_runtime(employee_id, name)
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
    employee_id: str,
    name: str,
    user_message: str,
    history: list[dict] | None = None,
    context: str | None = None,
    forced_skill: str | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[ExecutionEvent, None]:
    from engine.execution.agent_loop import reply_events_with_runtime

    runtime, services = _legacy_runtime(employee_id, name, session_id=session_id)
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
    employee_id: str,
    name: str,
    user_message: str,
    history: list[dict] | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    from engine.execution.agent_loop import reply_stream_with_runtime

    runtime, services = _legacy_runtime(employee_id, name, session_id=session_id)
    async for chunk in reply_stream_with_runtime(
        EngineRequest(message=user_message, history=history),
        runtime,
        services,
    ):
        yield chunk

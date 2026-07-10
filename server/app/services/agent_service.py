from __future__ import annotations

from typing import Any, AsyncGenerator

from engine.llm.model_config import SMITH_TEMPLATE_ID

from ..infrastructure.repositories.auto_task_repo import AutoTaskRepo
from ..infrastructure.repositories.agent_profile_repo import AgentProfileRepo
from ..infrastructure.repositories.session_repo import SessionRepo
from ..infrastructure.repositories.task_repo import TaskRepo
from ..schemas.agent_profile import AgentProfileOut, AgentProfileUpdate
from ..schemas.auto_task import AutoTaskCreate, AutoTaskRunOut, AutoTaskUpdate
from ..schemas.session import MessageOut, SessionOut
from ..schemas.task import TaskCreate, TaskOut
from .auto_task_service import AutoTaskService
from .agent_profile_service import AgentProfileService
from .profile_file_service import ProfileFileService
from .session_service import SessionService
from .skill_service import SkillService
from .stats_service import StatsService
from .task_service import TaskService

SMITH_NAME = "Smith"
SMITH_DESCRIPTION = (
    "面向个人工作流的常驻本地 Agent，负责理解目标、整理上下文、检索信息、"
    "规划执行并交付可落地结果。"
)


class AgentService:
    """Single-Smith facade over the agent-profile persistence model."""

    def __init__(
        self,
        *,
        agent_profile_service: AgentProfileService | Any | None = None,
        session_service: SessionService | Any | None = None,
        task_service: TaskService | Any | None = None,
        auto_task_service: AutoTaskService | Any | None = None,
        profile_file_service: ProfileFileService | Any | None = None,
        skill_service: SkillService | Any | None = None,
        stats_service: StatsService | Any | None = None,
    ) -> None:
        agent_profile_repo = AgentProfileRepo()
        session_repo = SessionRepo()
        auto_task_repo = AutoTaskRepo()
        self.agent_profile_service = agent_profile_service or AgentProfileService(agent_profile_repo)
        self.session_service = session_service or SessionService(session_repo, agent_profile_repo)
        self.task_service = task_service or TaskService(TaskRepo(), agent_profile_repo)
        self.auto_task_service = auto_task_service or AutoTaskService(
            auto_task_repo,
            agent_profile_repo,
            session_repo,
        )
        self.profile_file_service = profile_file_service or ProfileFileService()
        self.skill_service = skill_service or SkillService(agent_profile_repo)
        self.stats_service = stats_service or StatsService()

    async def ensure_profile(self) -> AgentProfileOut:
        from ..schemas.agent_profile import AgentProfileCreate

        for profile in await self.agent_profile_service.list_profiles():
            if profile.name == SMITH_NAME and profile.role == SMITH_TEMPLATE_ID:
                return AgentProfileOut(**profile.model_dump())

        created = await self.agent_profile_service.create_profile(
            AgentProfileCreate(
                name=SMITH_NAME,
                role=SMITH_TEMPLATE_ID,
                description=SMITH_DESCRIPTION,
            )
        )
        return AgentProfileOut(**created.model_dump())

    async def get_profile(self) -> AgentProfileOut:
        return await self.ensure_profile()

    async def update_profile(self, body: AgentProfileUpdate) -> AgentProfileOut:
        profile = await self.ensure_profile()
        updated = await self.agent_profile_service.update_profile(profile.id, body)
        return AgentProfileOut(**updated.model_dump())

    async def _profile_id(self) -> str:
        return (await self.ensure_profile()).id

    async def list_sessions(self) -> list[SessionOut]:
        return await self.session_service.list_sessions(await self._profile_id())

    async def create_session(self, title: str) -> SessionOut:
        return await self.session_service.create_session(await self._profile_id(), title)

    async def list_messages(
        self,
        session_id: str,
        *,
        limit: int = 0,
        offset: int = 0,
    ) -> list[MessageOut]:
        return await self.session_service.list_messages(
            session_id,
            limit=limit,
            offset=offset,
        )

    async def send_message(
        self,
        session_id: str,
        content: str,
        *,
        context: str | None = None,
        skill_name: str | None = None,
    ) -> MessageOut:
        return await self.session_service.send_message(
            await self._profile_id(),
            session_id,
            content,
            context=context,
            skill_name=skill_name,
        )

    async def stream_message(
        self,
        session_id: str,
        content: str,
        *,
        context: str | None = None,
        skill_name: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        async for event in self.session_service.stream_message(
            await self._profile_id(),
            session_id,
            content,
            context=context,
            skill_name=skill_name,
        ):
            yield event

    async def list_skills(self):
        return await self.skill_service.list_skills(await self._profile_id())

    async def list_files(self) -> list[dict]:
        return await self.profile_file_service.list_files(await self._profile_id())

    async def get_file(self, filename: str) -> dict:
        return await self.profile_file_service.get_file(await self._profile_id(), filename)

    async def update_file(self, filename: str, content: str) -> dict:
        return await self.profile_file_service.update_file(
            await self._profile_id(),
            filename,
            content,
        )

    async def get_stats(self) -> dict:
        return await self.stats_service.get_agent_stats(await self._profile_id())

    async def list_tasks(self) -> list[TaskOut]:
        return await self.task_service.list_tasks(await self._profile_id())

    async def create_task(self, body: TaskCreate) -> TaskOut:
        return await self.task_service.create_task(await self._profile_id(), body)

    async def list_auto_tasks(self):
        return await self.auto_task_service.list_auto_tasks(await self._profile_id())

    async def create_auto_task(self, body: AutoTaskCreate):
        return await self.auto_task_service.create_auto_task(
            await self._profile_id(),
            body,
        )

    async def update_auto_task(self, task_id: str, body: AutoTaskUpdate):
        return await self.auto_task_service.update_auto_task(task_id, body)

    async def trigger_auto_task(self, task_id: str) -> AutoTaskRunOut:
        return await self.auto_task_service.trigger_auto_task(task_id)

    async def delete_auto_task(self, task_id: str) -> None:
        await self.auto_task_service.delete_auto_task(task_id)

    async def list_runs(self, task_id: str):
        return await self.auto_task_service.list_runs(task_id)

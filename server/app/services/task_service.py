from __future__ import annotations

from fastapi import HTTPException

from ..schemas.task import TaskCreate, TaskOut
from ..infrastructure.repositories.task_repo import TaskRepo
from ..infrastructure.repositories.agent_profile_repo import AgentProfileRepo


class TaskService:

    def __init__(self, task_repo: TaskRepo, agent_profile_repo: AgentProfileRepo) -> None:
        self.task_repo = task_repo
        self.agent_profile_repo = agent_profile_repo

    async def list_tasks(self, agent_id: str) -> list[TaskOut]:
        rows = await self.task_repo.list_by_agent(agent_id)
        return [TaskOut(**r) for r in rows]

    async def create_task(self, agent_id: str, body: TaskCreate) -> TaskOut:
        emp = await self.agent_profile_repo.get(agent_id)
        if emp is None:
            raise HTTPException(404, "Agent profile not found")
        row = await self.task_repo.create(agent_id, body.type, body.title)
        return TaskOut(**row)

from __future__ import annotations

import json
import re
from typing import AsyncGenerator

from fastapi import HTTPException

from engine.execution.agent_loop import (
    reply_stream_with_runtime as engine_reply_stream_with_runtime,
    reply_with_runtime as engine_reply_with_runtime,
)
from engine.execution.runtime import EngineRequest
from engine.prompt.assembler import build_team_context

from ..schemas.team import TeamGroupOut, TeamMessageOut
from ..infrastructure.repositories.team_repo import TeamRepo
from ..infrastructure.repositories.agent_profile_repo import AgentProfileRepo
from .engine_runtime import build_engine_runtime


class TeamService:

    def __init__(self, team_repo: TeamRepo, agent_profile_repo: AgentProfileRepo) -> None:
        self.team_repo = team_repo
        self.agent_profile_repo = agent_profile_repo

    # ── Groups ──────────────────────────────────────────────

    async def create_group(
        self, name: str, description: str, member_ids: list[str]
    ) -> TeamGroupOut:
        # Validate all member IDs exist
        for mid in member_ids:
            emp = await self.agent_profile_repo.get(mid)
            if emp is None:
                raise HTTPException(404, f"Agent profile not found: {mid}")
        row = await self.team_repo.create_group(name, description, member_ids)
        return TeamGroupOut(**row)

    async def list_groups(self) -> list[TeamGroupOut]:
        rows = await self.team_repo.list_groups()
        return [TeamGroupOut(**r) for r in rows]

    async def get_group(self, group_id: str) -> TeamGroupOut:
        row = await self.team_repo.get_group(group_id)
        if row is None:
            raise HTTPException(404, "Team group not found")
        return TeamGroupOut(**row)

    async def delete_group(self, group_id: str) -> None:
        deleted = await self.team_repo.delete_group(group_id)
        if not deleted:
            raise HTTPException(404, "Team group not found")

    # ── Messages ────────────────────────────────────────────

    async def get_messages(self, group_id: str, limit: int = 50) -> list[TeamMessageOut]:
        group = await self.team_repo.get_group(group_id)
        if group is None:
            raise HTTPException(404, "Team group not found")
        rows = await self.team_repo.get_messages(group_id, limit=limit)
        return [TeamMessageOut(**r) for r in rows]

    async def send_message(
        self, group_id: str, content: str
    ) -> list[TeamMessageOut]:
        """Send a user message to the team, then route to @mentioned agents.

        Returns the list of all new messages (user + agent replies).
        """
        group = await self.team_repo.get_group(group_id)
        if group is None:
            raise HTTPException(404, "Team group not found")

        mentions = self._extract_mentions(content, group["member_ids"])

        # Save the user message
        user_msg = await self.team_repo.add_message(
            group_id, "user", "用户", content, mentions,
        )
        result = [TeamMessageOut(**user_msg)]

        # Route to each mentioned agent (or all members if no mentions)
        targets = mentions if mentions else group["member_ids"]
        replies = await self._route_to_agents(group, targets, content)
        result.extend(replies)

        return result

    async def stream_message(
        self, group_id: str, content: str
    ) -> AsyncGenerator[dict, None]:
        """SSE streaming version of send_message."""
        group = await self.team_repo.get_group(group_id)
        if group is None:
            raise HTTPException(404, "Team group not found")

        mentions = self._extract_mentions(content, group["member_ids"])

        # Save user message
        user_msg = await self.team_repo.add_message(
            group_id, "user", "用户", content, mentions,
        )
        yield {
            "event": "user_message",
            "data": json.dumps(
                {"id": user_msg["id"], "content": content}, ensure_ascii=False
            ),
        }

        # Route to mentioned agents (or all if no mentions)
        targets = mentions if mentions else group["member_ids"]

        for emp_id in targets:
            emp = await self.agent_profile_repo.get(emp_id)
            if emp is None:
                continue
            emp_name = emp["name"]

            # Build team context for the agent
            recent = await self.team_repo.get_messages(group_id, limit=20)
            members = await self._resolve_member_names(group["member_ids"])
            team_ctx = build_team_context(group["name"], members, recent)
            augmented = f"{team_ctx}\n\n---\n\n{content}"

            yield {
                "event": "agent_start",
                "data": json.dumps(
                    {"agent_id": emp_id, "name": emp_name}, ensure_ascii=False
                ),
            }

            runtime, services = build_engine_runtime(emp_id, emp_name)
            request = EngineRequest(message=augmented)
            full_reply: list[str] = []
            async for chunk in engine_reply_stream_with_runtime(request, runtime, services):
                full_reply.append(chunk)
                yield {
                    "event": "message",
                    "data": json.dumps(
                        {"agent_id": emp_id, "text": chunk}, ensure_ascii=False
                    ),
                }

            reply_text = "".join(full_reply)
            saved = await self.team_repo.add_message(
                group_id, emp_id, emp_name, reply_text, [],
            )
            yield {
                "event": "agent_done",
                "data": json.dumps(
                    {"id": saved["id"], "agent_id": emp_id, "name": emp_name},
                    ensure_ascii=False,
                ),
            }

        yield {"event": "done", "data": "{}"}

    # ── Internal helpers ────────────────────────────────────

    async def _route_to_agents(
        self, group: dict, target_ids: list[str], user_content: str
    ) -> list[TeamMessageOut]:
        """Call engine reply for each target agent and save their responses."""
        results: list[TeamMessageOut] = []

        recent = await self.team_repo.get_messages(group["id"], limit=20)
        members = await self._resolve_member_names(group["member_ids"])
        team_ctx = build_team_context(group["name"], members, recent)
        augmented = f"{team_ctx}\n\n---\n\n{user_content}"

        for emp_id in target_ids:
            emp = await self.agent_profile_repo.get(emp_id)
            if emp is None:
                continue
            emp_name = emp["name"]

            runtime, services = build_engine_runtime(emp_id, emp_name)
            result = await engine_reply_with_runtime(
                EngineRequest(message=augmented),
                runtime,
                services,
            )
            reply_text = result.text

            saved = await self.team_repo.add_message(
                group["id"], emp_id, emp_name, reply_text, [],
            )
            results.append(TeamMessageOut(**saved))

        return results

    async def _resolve_member_names(self, member_ids: list[str]) -> list[str]:
        names: list[str] = []
        for mid in member_ids:
            emp = await self.agent_profile_repo.get(mid)
            names.append(emp["name"] if emp else mid)
        return names

    @staticmethod
    def _extract_mentions(content: str, member_ids: list[str]) -> list[str]:
        """Extract @agent_id mentions from message content."""
        found: list[str] = []
        for mid in member_ids:
            if f"@{mid}" in content:
                found.append(mid)
        return found

from __future__ import annotations

from fastapi import HTTPException

from ..infrastructure.profile_files import (
    agent_profile_dir,
    list_agent_profile_files,
    read_agent_profile_file,
    write_agent_profile_file,
)


ALLOWED_PROFILE_FILES = {
    "role.md",
    "style.md",
    "workflow.md",
    "toolbox.md",
    "context.md",
    "config.yaml",
}


class ProfileFileService:
    async def list_files(self, agent_id: str) -> list[dict]:
        d = agent_profile_dir(agent_id)
        if not d.exists():
            raise HTTPException(404, "Agent profile not found")
        return list_agent_profile_files(agent_id)

    async def get_file(self, agent_id: str, filename: str) -> dict:
        self._ensure_allowed(filename)
        content = read_agent_profile_file(agent_id, filename)
        if content is None:
            raise HTTPException(404, "File not found")
        return {"filename": filename, "content": content}

    async def update_file(self, agent_id: str, filename: str, content: str) -> dict:
        self._ensure_allowed(filename)
        if not agent_profile_dir(agent_id).exists():
            raise HTTPException(404, "Agent profile not found")
        write_agent_profile_file(agent_id, filename, content)
        return {"filename": filename, "content": content}

    @staticmethod
    def _ensure_allowed(filename: str) -> None:
        if filename not in ALLOWED_PROFILE_FILES:
            allowed = ", ".join(sorted(ALLOWED_PROFILE_FILES))
            raise HTTPException(400, f"File not allowed. Allowed: {allowed}")

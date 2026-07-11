from __future__ import annotations

from fastapi import HTTPException

from ..infrastructure.profile_files import (
    list_smith_profile_files,
    read_smith_profile_file,
    smith_profile_dir,
    write_smith_profile_file,
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
    async def list_files(self) -> list[dict]:
        d = smith_profile_dir()
        if not d.exists():
            raise HTTPException(404, "Agent profile not found")
        return list_smith_profile_files()

    async def get_file(self, filename: str) -> dict:
        self._ensure_allowed(filename)
        content = read_smith_profile_file(filename)
        if content is None:
            raise HTTPException(404, "File not found")
        return {"filename": filename, "content": content}

    async def update_file(self, filename: str, content: str) -> dict:
        self._ensure_allowed(filename)
        if not smith_profile_dir().exists():
            raise HTTPException(404, "Agent profile not found")
        write_smith_profile_file(filename, content)
        return {"filename": filename, "content": content}

    @staticmethod
    def _ensure_allowed(filename: str) -> None:
        if filename not in ALLOWED_PROFILE_FILES:
            allowed = ", ".join(sorted(ALLOWED_PROFILE_FILES))
            raise HTTPException(400, f"File not allowed. Allowed: {allowed}")

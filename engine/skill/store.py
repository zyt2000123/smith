"""Version-controlled skill storage for agent-installed skills.

Each agent's skills live under the agent profile's skills dir (…/<id>/skills/).
Layout per skill:

    skills/<name>/SKILL.md          # current version
    skills/<name>/.versions/        # timestamped snapshots
        20260704T120000.md
        20260704T130000.md
        ...

Only the last 10 versions are kept.
"""

from __future__ import annotations

import difflib
from datetime import datetime, timezone
from pathlib import Path


_MAX_VERSIONS = 10


class SkillStore:
    """Version-controlled skill storage for agent-installed skills."""

    def __init__(self, skills_dir: Path) -> None:
        self._dir = skills_dir  # agent profile skills dir: …/<id>/skills/

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _skill_dir(self, skill_name: str) -> Path:
        safe = Path(skill_name).name  # prevent path traversal
        return self._dir / safe

    def _skill_file(self, skill_name: str) -> Path:
        return self._skill_dir(skill_name) / "SKILL.md"

    def _versions_dir(self, skill_name: str) -> Path:
        return self._skill_dir(skill_name) / ".versions"

    def _prune(self, skill_name: str) -> None:
        """Keep only the last _MAX_VERSIONS snapshots."""
        vdir = self._versions_dir(skill_name)
        if not vdir.is_dir():
            return
        versions = sorted(vdir.glob("*.md"))
        while len(versions) > _MAX_VERSIONS:
            versions.pop(0).unlink()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def save_version(self, skill_name: str, content: str) -> str:
        """Save current SKILL.md as a numbered version, return version id.

        *content* is the text that is about to be replaced (the old version).
        """
        vdir = self._versions_dir(skill_name)
        vdir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        version_id = ts
        target = vdir / f"{version_id}.md"

        # Avoid collision (unlikely but safe)
        seq = 0
        while target.exists():
            seq += 1
            version_id = f"{ts}_{seq}"
            target = vdir / f"{version_id}.md"

        target.write_text(content, encoding="utf-8")
        self._prune(skill_name)
        return version_id

    async def rollback(self, skill_name: str, version_id: str) -> bool:
        """Restore a previous version of a skill."""
        safe_vid = Path(version_id).name
        snapshot = self._versions_dir(skill_name) / f"{safe_vid}.md"
        if not snapshot.is_file():
            return False

        skill_file = self._skill_file(skill_name)
        if not skill_file.is_file():
            return False

        # Save current as a version before rolling back
        current = skill_file.read_text(encoding="utf-8")
        await self.save_version(skill_name, current)

        # Restore
        skill_file.write_text(snapshot.read_text(encoding="utf-8"), encoding="utf-8")
        return True

    async def list_versions(self, skill_name: str) -> list[dict]:
        """List available versions with timestamps."""
        vdir = self._versions_dir(skill_name)
        if not vdir.is_dir():
            return []

        result: list[dict] = []
        for f in sorted(vdir.glob("*.md")):
            result.append({
                "version_id": f.stem,
                "timestamp": f.stem.replace("T", " "),
                "size": f.stat().st_size,
            })
        return result

    async def diff(self, skill_name: str, v1: str, v2: str) -> str:
        """Show unified diff between two versions.

        v1/v2 can be version ids or the special value "current" for the
        live SKILL.md.
        """
        def _read(vid: str) -> list[str]:
            if vid == "current":
                p = self._skill_file(skill_name)
            else:
                safe = Path(vid).name
                p = self._versions_dir(skill_name) / f"{safe}.md"
            if not p.is_file():
                raise FileNotFoundError(f"Version '{vid}' not found")
            return p.read_text(encoding="utf-8").splitlines(keepends=True)

        lines_a = _read(v1)
        lines_b = _read(v2)

        diff_lines = difflib.unified_diff(
            lines_a, lines_b,
            fromfile=f"{skill_name}@{v1}",
            tofile=f"{skill_name}@{v2}",
        )
        result = "".join(diff_lines)
        return result if result else "(no differences)"

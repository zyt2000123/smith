"""File snapshot — backup files before modification, support rewind."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path


class FileSnapshot:
    """Track and backup files before they are modified by Agent tools.

    Usage:
        snap = FileSnapshot(session_id)
        snap.track(path)         # call BEFORE write_file/edit
        snap.rewind(path)        # restore to pre-modification state
        snap.rewind_all()        # restore all tracked files
    """

    def __init__(self, session_id: str = "default"):
        try:
            from common.config import DATA_DIR
            self._backup_dir = DATA_DIR / "snapshots" / session_id
        except Exception:
            self._backup_dir = Path.home() / ".agent-smith" / "snapshots" / session_id
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._tracked: dict[str, list[str]] = {}

    def _backup_name(self, filepath: str, version: int) -> str:
        h = hashlib.sha256(filepath.encode()).hexdigest()[:16]
        return f"{h}_v{version}"

    def track(self, filepath: str) -> bool:
        """Backup a file before it gets modified. Returns True if backup was created."""
        resolved = os.path.realpath(filepath)
        if not os.path.isfile(resolved):
            self._tracked.setdefault(resolved, []).append("")
            return True

        versions = self._tracked.get(resolved, [])
        version = len(versions) + 1
        backup_name = self._backup_name(resolved, version)
        backup_path = self._backup_dir / backup_name

        try:
            shutil.copy2(resolved, backup_path)
            versions.append(backup_name)
            self._tracked[resolved] = versions
            return True
        except Exception:
            return False

    def rewind(self, filepath: str) -> bool:
        """Restore a file to its state before the last modification."""
        resolved = os.path.realpath(filepath)
        versions = self._tracked.get(resolved, [])
        if not versions:
            return False

        backup_name = versions[-1]
        if not backup_name:
            if os.path.exists(resolved):
                os.remove(resolved)
            return True

        backup_path = self._backup_dir / backup_name
        if not backup_path.is_file():
            return False

        try:
            os.makedirs(os.path.dirname(resolved), exist_ok=True)
            shutil.copy2(str(backup_path), resolved)
            return True
        except Exception:
            return False

    def rewind_all(self) -> dict[str, bool]:
        """Restore all tracked files. Returns {path: success}."""
        return {path: self.rewind(path) for path in self._tracked}

    def list_tracked(self) -> list[dict]:
        """List all tracked files with version counts."""
        return [
            {"path": path, "versions": len(versions)}
            for path, versions in self._tracked.items()
        ]


_active_snapshots: dict[str, FileSnapshot] = {}


def get_snapshot(session_id: str = "default") -> FileSnapshot:
    if session_id not in _active_snapshots:
        _active_snapshots[session_id] = FileSnapshot(session_id)
    return _active_snapshots[session_id]

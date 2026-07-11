"""Session state checkpoint for crash recovery.

Saves execution state to a JSON file after each significant step.
On restart, ``restore()`` returns the last checkpoint so execution can resume.
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, asdict

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass
class SessionCheckpoint:
    agent_id: str
    session_id: str
    identity_id: str
    route_id: str
    skill_chain_index: int  # -1 for DIRECT
    context: dict  # accumulated skill outputs
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SessionCheckpoint":
        return cls(**d)


class SessionStateManager:
    """Persist and restore session execution state."""

    def __init__(self, agent_dir: Path):
        self._state_dir = agent_dir / "sessions" / ".state"
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        if not _SESSION_ID_RE.match(session_id):
            raise ValueError(f"invalid session_id: {session_id!r}")
        p = (self._state_dir / f"{session_id}.json").resolve()
        if not p.is_relative_to(self._state_dir.resolve()):
            raise ValueError("session_id escapes state dir")
        return p

    def save(self, checkpoint: SessionCheckpoint) -> None:
        path = self._path(checkpoint.session_id)
        path.write_text(
            json.dumps(checkpoint.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def restore(self, session_id: str) -> SessionCheckpoint | None:
        path = self._path(session_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SessionCheckpoint.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def clear(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.is_file():
            path.unlink()

    def list_active(self) -> list[SessionCheckpoint]:
        """List all sessions with saved state (crashed/interrupted)."""
        results = []
        for f in self._state_dir.glob("*.json"):
            cp = self.restore(f.stem)
            if cp:
                results.append(cp)
        return results

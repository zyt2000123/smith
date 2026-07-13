"""Durable lifecycle state for one Agent execution.

RunState is intentionally smaller than a conversation/session snapshot.  It
tracks where an execution is in its lifecycle and a few bounded progress
fields, but it does not persist model messages or raw tool arguments.  That
keeps the state safe to expose for status polling and avoids accidental
re-execution of side-effectful tools during a future resume flow.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4

from common.paths import PRIVATE_DIR_MODE, PRIVATE_FILE_MODE


class RunStatus(str, Enum):
    """Lifecycle states that can be observed for one execution."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStateError(RuntimeError):
    """Base error for invalid or unreadable persisted run state."""


class RunStateTransitionError(RunStateError):
    """Raised when a run tries to skip or leave an invalid lifecycle state."""


_ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({
        RunStatus.RUNNING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }),
    RunStatus.RUNNING: frozenset({
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
        RunStatus.COMPLETED,
        RunStatus.INCOMPLETE,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }),
    RunStatus.WAITING_APPROVAL: frozenset({
        RunStatus.RUNNING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }),
    RunStatus.COMPLETED: frozenset({RunStatus.COMPLETED}),
    RunStatus.INCOMPLETE: frozenset({RunStatus.INCOMPLETE}),
    RunStatus.FAILED: frozenset({RunStatus.FAILED}),
    RunStatus.CANCELLED: frozenset({RunStatus.CANCELLED}),
}

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_text(value: object | None, *, limit: int = 200) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:limit] or None


@dataclass
class RunState:
    """Persisted metadata for one execution attempt."""

    run_id: str
    agent_id: str
    session_id: str | None = None
    identity_id: str | None = None
    status: RunStatus = RunStatus.QUEUED
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    event_seq: int = 0
    last_event_type: str | None = None
    current_skill: str | None = None
    current_tool: str | None = None
    reason: str | None = None
    error: str | None = None

    def transition(
        self,
        status: RunStatus | str,
        *,
        reason: str | None = None,
        error: str | None = None,
    ) -> None:
        target = RunStatus(status)
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise RunStateTransitionError(
                f"Cannot transition run {self.run_id!r} from "
                f"{self.status.value!r} to {target.value!r}"
            )
        self.status = target
        if reason is not None:
            self.reason = _bounded_text(reason)
        if error is not None:
            self.error = _bounded_text(error)
        self.updated_at = _now()

    def record_event(
        self,
        event_type: str,
        *,
        current_skill: str | None = None,
        current_tool: str | None = None,
        clear_skill: bool = False,
        clear_tool: bool = False,
    ) -> None:
        self.event_seq += 1
        self.last_event_type = _bounded_text(event_type)
        if current_skill is not None:
            self.current_skill = _bounded_text(current_skill)
        elif clear_skill:
            self.current_skill = None
        if current_tool is not None:
            self.current_tool = _bounded_text(current_tool)
        elif clear_tool:
            self.current_tool = None
        self.updated_at = _now()

    def to_dict(self) -> dict[str, object | None]:
        return {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "identity_id": self.identity_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "event_seq": self.event_seq,
            "last_event_type": self.last_event_type,
            "current_skill": self.current_skill,
            "current_tool": self.current_tool,
            "reason": self.reason,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "RunState":
        try:
            run_id = str(data["run_id"])
            agent_id = str(data["agent_id"])
            status = RunStatus(str(data["status"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise RunStateError("Invalid persisted run state") from exc

        event_seq = data.get("event_seq", 0)
        try:
            parsed_event_seq = max(0, int(event_seq))
        except (TypeError, ValueError) as exc:
            raise RunStateError("Invalid persisted run event sequence") from exc

        return cls(
            run_id=run_id,
            agent_id=agent_id,
            session_id=_bounded_text(data.get("session_id")),
            identity_id=_bounded_text(data.get("identity_id")),
            status=status,
            created_at=str(data.get("created_at") or _now()),
            updated_at=str(data.get("updated_at") or _now()),
            event_seq=parsed_event_seq,
            last_event_type=_bounded_text(data.get("last_event_type")),
            current_skill=_bounded_text(data.get("current_skill")),
            current_tool=_bounded_text(data.get("current_tool")),
            reason=_bounded_text(data.get("reason")),
            error=_bounded_text(data.get("error")),
        )


class RunStateStore:
    """Atomic, private JSON persistence for run metadata."""

    def __init__(self, profile_dir: Path) -> None:
        self.root = Path(profile_dir) / "runs"
        self.root.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIR_MODE)
        self.root.chmod(PRIVATE_DIR_MODE)

    @staticmethod
    def _validate_run_id(run_id: str) -> str:
        if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
            raise ValueError("invalid run id")
        return run_id

    def _path(self, run_id: str) -> Path:
        return self.root / f"{self._validate_run_id(run_id)}.json"

    def create(
        self,
        run_id: str,
        *,
        agent_id: str,
        session_id: str | None = None,
        identity_id: str | None = None,
    ) -> RunState:
        path = self._path(run_id)
        if path.exists():
            raise RunStateError(f"Run state already exists for {run_id!r}")
        state = RunState(
            run_id=run_id,
            agent_id=_bounded_text(agent_id) or "unknown",
            session_id=_bounded_text(session_id),
            identity_id=_bounded_text(identity_id),
        )
        self.save(state)
        return state

    def get(self, run_id: str) -> RunState | None:
        path = self._path(run_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RunStateError(f"Unable to read run state for {run_id!r}") from exc
        if not isinstance(data, dict):
            raise RunStateError(f"Invalid run state payload for {run_id!r}")
        state = RunState.from_dict(data)
        if state.run_id != run_id:
            raise RunStateError(f"Run state id mismatch for {run_id!r}")
        return state

    def save(self, state: RunState) -> None:
        path = self._path(state.run_id)
        payload = json.dumps(
            state.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        temp_path = self.root / f".{state.run_id}.{uuid4().hex}.tmp"
        try:
            fd = os.open(
                temp_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                PRIVATE_FILE_MODE,
            )
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            path.chmod(PRIVATE_FILE_MODE)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise RunStateError(f"Unable to save run state for {state.run_id!r}") from exc

    def transition(
        self,
        run_id: str,
        status: RunStatus | str,
        *,
        event_type: str | None = None,
        reason: str | None = None,
        error: str | None = None,
    ) -> RunState:
        state = self._require(run_id)
        if event_type is not None:
            state.record_event(event_type)
        state.transition(status, reason=reason, error=error)
        self.save(state)
        return state

    def record_event(
        self,
        run_id: str,
        event_type: str,
        *,
        current_skill: str | None = None,
        current_tool: str | None = None,
        clear_skill: bool = False,
        clear_tool: bool = False,
    ) -> RunState:
        state = self._require(run_id)
        state.record_event(
            event_type,
            current_skill=current_skill,
            current_tool=current_tool,
            clear_skill=clear_skill,
            clear_tool=clear_tool,
        )
        self.save(state)
        return state

    def _require(self, run_id: str) -> RunState:
        state = self.get(run_id)
        if state is None:
            raise RunStateError(f"Run state not found for {run_id!r}")
        return state

"""Unified policy layer for deciding whether tool calls may execute."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from engine.safety.tool_guard import PermissionLevel
from engine.tool.interface import ToolCall

if TYPE_CHECKING:
    from engine.safety.tool_guard import ToolGuard


@dataclass(frozen=True)
class ToolPolicyDecision:
    allowed: bool
    reason: str = ""
    level: PermissionLevel = PermissionLevel.READ
    needs_confirmation: bool = False

    @property
    def observation(self) -> str:
        if self.allowed:
            return ""
        return f"[BLOCKED] {self.reason}"


class ToolPolicy:
    """Single policy gateway used before any runtime tool execution."""

    def __init__(self, guard: "ToolGuard | None" = None) -> None:
        self._guard = guard

    def evaluate(self, call: ToolCall) -> ToolPolicyDecision:
        if self._guard is None:
            return ToolPolicyDecision(allowed=True)

        guard_result = self._guard.check(call)
        return ToolPolicyDecision(
            allowed=guard_result.allowed,
            reason=guard_result.reason,
            level=guard_result.level,
            needs_confirmation=guard_result.needs_confirmation,
        )

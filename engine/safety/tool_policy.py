"""Unified policy layer for deciding whether tool calls may execute."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from engine.safety.fact_gate import FactGate
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
    challenged: bool = False

    @property
    def observation(self) -> str:
        if self.allowed:
            return ""
        if self.challenged:
            return f"[PREFLIGHT] {self.reason}"
        return f"[BLOCKED] {self.reason}"


class ToolPolicy:
    """Single policy gateway used before any runtime tool execution."""

    def __init__(
        self,
        guard: "ToolGuard | None" = None,
        *,
        fact_gate: FactGate | None = None,
    ) -> None:
        self._guard = guard
        self._fact_gate = fact_gate

    def evaluate(self, call: ToolCall) -> ToolPolicyDecision:
        if self._guard is not None:
            guard_result = self._guard.check(call)
            if not guard_result.allowed:
                return ToolPolicyDecision(
                    allowed=False,
                    reason=guard_result.reason,
                    level=guard_result.level,
                    needs_confirmation=guard_result.needs_confirmation,
                )
            level = guard_result.level
        else:
            level = PermissionLevel.READ

        if self._fact_gate is not None:
            gate_result = self._fact_gate.evaluate(call)
            if gate_result.challenged:
                return ToolPolicyDecision(
                    allowed=False,
                    reason=gate_result.reason,
                    level=level,
                    challenged=True,
                )

        return ToolPolicyDecision(allowed=True, level=level)

    def begin_round(self) -> None:
        if self._fact_gate is not None:
            self._fact_gate.begin_round()

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class FailureSignature:
    error_type: str
    context_hash: str


class FailureLoopGuard:
    """Detect repeated failures and decide whether to retry, switch strategy, or block."""

    def __init__(self, max_same: int = 2, max_strategies: int = 2) -> None:
        self.max_same = max_same
        self.max_strategies = max_strategies
        self._counts: dict[str, int] = {}
        self._strategies_tried: set[str] = set()

    def record(self, sig: FailureSignature) -> Literal["retry", "switch", "blocked"]:
        key = f"{sig.error_type}:{sig.context_hash}"
        self._counts[key] = self._counts.get(key, 0) + 1
        self._strategies_tried.add(sig.error_type)

        if self._counts[key] < self.max_same:
            return "retry"

        if len(self._strategies_tried) >= self.max_strategies:
            return "blocked"

        return "switch"

    def reset(self) -> None:
        self._counts.clear()
        self._strategies_tried.clear()

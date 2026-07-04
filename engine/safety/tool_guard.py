from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from tool.interface import ToolCall


@dataclass
class GuardResult:
    allowed: bool
    reason: str = ""


class ToolGuard:
    """Match tool call arguments against dangerous-command patterns."""

    def __init__(self, rules_path: Path) -> None:
        self._rules: list[dict] = []
        if rules_path.is_file():
            self._rules = json.loads(rules_path.read_text(encoding="utf-8"))

    def check(self, tool_call: ToolCall) -> GuardResult:
        args_str = json.dumps(tool_call.arguments)
        for rule in self._rules:
            # Scope check: if rule specifies tools, only apply to those
            scoped_tools = rule.get("tools")
            if scoped_tools and tool_call.name not in scoped_tools:
                continue

            # Support both singular "pattern" and plural "patterns" (array)
            patterns = rule.get("patterns", [])
            single = rule.get("pattern", "")
            if single:
                patterns = [single] + list(patterns)

            exclude_patterns = rule.get("excludePatterns", [])

            for pattern in patterns:
                if not pattern:
                    continue
                if not re.search(pattern, args_str):
                    continue
                # Check exclusions before blocking
                excluded = any(
                    ep and re.search(ep, args_str)
                    for ep in exclude_patterns
                )
                if excluded:
                    continue
                reason = rule.get("reason") or rule.get("description") or f"Blocked by pattern: {pattern}"
                return GuardResult(allowed=False, reason=f"[{rule.get('id', '?')}] {reason}")

        return GuardResult(allowed=True)

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


class FileGuard:
    """Restrict file operations to allowed directories."""

    _SENSITIVE = frozenset({".ssh", ".gnupg", ".aws", ".kube"})

    def __init__(self, allowed_dirs: list[Path] | None = None):
        if allowed_dirs:
            self._allowed = [p.resolve() for p in allowed_dirs]
        else:
            # Default: home dir, /tmp, cwd
            self._allowed = [
                Path.home().resolve(),
                Path("/tmp").resolve(),
                Path.cwd().resolve(),
            ]

    def check_path(self, path_str: str) -> GuardResult:
        try:
            target = Path(path_str).resolve()
        except (ValueError, OSError):
            return GuardResult(allowed=False, reason=f"Invalid path: {path_str}")

        # Block known sensitive directories regardless
        for part in target.parts:
            if part in self._SENSITIVE:
                return GuardResult(allowed=False, reason=f"Access to {part}/ is blocked")

        if any(target.is_relative_to(d) for d in self._allowed):
            return GuardResult(allowed=True)

        return GuardResult(allowed=False, reason=f"Path {path_str} is outside allowed directories")


class ToolGuard:
    """Match tool call arguments against dangerous-command patterns."""

    # Tools whose arguments may contain file paths to guard
    _FILE_TOOLS = frozenset({"read_file", "write_file", "shell"})

    # Regex to extract absolute paths from shell command strings
    _ABS_PATH_RE = re.compile(r"(?<!\w)/(?:[a-zA-Z0-9_.~-]+/)+[a-zA-Z0-9_.~-]+")

    def __init__(self, rules_path: Path, allowed_dirs: list[Path] | None = None) -> None:
        self._rules: list[dict] = []
        if rules_path.is_file():
            self._rules = json.loads(rules_path.read_text(encoding="utf-8"))
        self.file_guard = FileGuard(allowed_dirs)

    def _check_file_paths(self, tool_call: ToolCall) -> GuardResult | None:
        """Run FileGuard on paths extracted from file/shell tool calls."""
        if tool_call.name not in self._FILE_TOOLS:
            return None

        paths_to_check: list[str] = []
        if tool_call.name in ("read_file", "write_file"):
            path_val = tool_call.arguments.get("path") or tool_call.arguments.get("file_path", "")
            if path_val:
                paths_to_check.append(path_val)
        elif tool_call.name == "shell":
            cmd = tool_call.arguments.get("command", "")
            paths_to_check.extend(self._ABS_PATH_RE.findall(cmd))

        for p in paths_to_check:
            result = self.file_guard.check_path(p)
            if not result.allowed:
                return result
        return None

    def check(self, tool_call: ToolCall) -> GuardResult:
        # File path guard — checked before pattern rules
        file_result = self._check_file_paths(tool_call)
        if file_result is not None:
            return file_result

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

"""Tool safety guard — permission levels, path checking, audit logging."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from tool.interface import ToolCall


# ── Permission Levels (req #2: default-deny + tiered approval) ──

class PermissionLevel(Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DESTRUCTIVE = "destructive"


TOOL_PERMISSIONS: dict[str, PermissionLevel] = {
    "read_file": PermissionLevel.READ,
    "grep": PermissionLevel.READ,
    "glob_files": PermissionLevel.READ,
    "list_dir": PermissionLevel.READ,
    "web_search": PermissionLevel.READ,
    "web_fetch": PermissionLevel.READ,
    "memory_ops": PermissionLevel.READ,
    "skill_load": PermissionLevel.READ,
    "todo": PermissionLevel.READ,
    "write_file": PermissionLevel.WRITE,
    "edit_file": PermissionLevel.WRITE,
    "skill_manage": PermissionLevel.WRITE,
    "git_ops": PermissionLevel.WRITE,
    "shell": PermissionLevel.EXECUTE,
}


@dataclass
class GuardResult:
    allowed: bool
    reason: str = ""
    level: PermissionLevel = PermissionLevel.READ
    needs_confirmation: bool = False


# ── Path guard (req #3: symlink, traversal, sensitive files) ──

class FileGuard:
    _ALWAYS_BLOCKED = frozenset({".ssh", ".gnupg", ".aws", ".kube"})
    _SENSITIVE_WRITE = frozenset({".env", ".env.local", ".env.production", ".npmrc", ".pypirc"})
    _SENSITIVE_DIRS = frozenset({".git"})

    def __init__(self, allowed_dirs: list[Path] | None = None):
        if allowed_dirs:
            self._allowed = [p.resolve() for p in allowed_dirs]
        else:
            self._allowed = [Path.home().resolve(), Path("/tmp").resolve(), Path.cwd().resolve()]

    def check_path(self, path_str: str, writing: bool = False) -> GuardResult:
        try:
            target = Path(path_str).resolve()
        except (ValueError, OSError):
            return GuardResult(allowed=False, reason=f"Invalid path: {path_str}")

        for part in target.parts:
            if part in self._ALWAYS_BLOCKED:
                return GuardResult(allowed=False, reason=f"Access to {part}/ is blocked")

        if writing:
            name = target.name.lower()
            if name in self._SENSITIVE_WRITE or name.startswith(".env"):
                return GuardResult(allowed=False, reason=f"Write to sensitive file blocked: {name}", needs_confirmation=True)
            for part in target.parts:
                if part in self._SENSITIVE_DIRS:
                    return GuardResult(allowed=False, reason=f"Write inside {part}/ is blocked", needs_confirmation=True)

        if any(target.is_relative_to(d) for d in self._allowed):
            return GuardResult(allowed=True)

        return GuardResult(allowed=False, reason=f"Path {path_str} outside allowed directories")


# ── Audit log (req #6: every tool call logged) ──────────────

class AuditLog:
    def __init__(self, log_path: Optional[Path] = None):
        if log_path is None:
            try:
                from common.config import DATA_DIR
                log_path = DATA_DIR / "audit.jsonl"
            except Exception:
                log_path = Path.home() / ".agent-smith" / "audit.jsonl"
        self._path = log_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, tool_name: str, arguments: dict, result: GuardResult, **extra: object) -> None:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "tool": tool_name,
            "args_summary": _summarize_args(arguments),
            "allowed": result.allowed,
            "level": result.level.value,
            "reason": result.reason or None,
            **extra,
        }
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


def _summarize_args(args: dict, max_len: int = 200) -> dict:
    redacted = {}
    for k, v in args.items():
        if k in ("api_key", "password", "secret", "token"):
            redacted[k] = "***"
        elif isinstance(v, str) and len(v) > max_len:
            redacted[k] = v[:max_len] + f"...({len(v)} chars)"
        else:
            redacted[k] = v
    return redacted


# ── Session whitelist (req #5: session-scoped overrides) ────

class SessionWhitelist:
    def __init__(self) -> None:
        self._allowed_tools: set[str] = set()
        self._allowed_paths: set[str] = set()

    def allow_tool(self, tool_name: str) -> None:
        self._allowed_tools.add(tool_name)

    def allow_path(self, path: str) -> None:
        self._allowed_paths.add(str(Path(path).resolve()))

    def is_tool_allowed(self, tool_name: str) -> bool:
        return tool_name in self._allowed_tools

    def is_path_allowed(self, path: str) -> bool:
        try:
            resolved = Path(path).resolve()
        except (ValueError, OSError):
            return False
        for p in self._allowed_paths:
            base = Path(p)
            try:
                if resolved == base or resolved.is_relative_to(base):
                    return True
            except ValueError:
                continue
        return False

    def clear(self) -> None:
        self._allowed_tools.clear()
        self._allowed_paths.clear()


# ── Shell path extraction (req #4: redirects + pipes) ───────

_REDIRECT_RE = re.compile(r"(?:>>?|[12]>>?)\s*([^\s;|&]+)")
_ABS_PATH_RE = re.compile(r"(?<!\w)/(?:[a-zA-Z0-9_.~-]+/)+[a-zA-Z0-9_.~-]+")


def _extract_shell_paths(command: str) -> tuple[list[str], list[str]]:
    read_paths = _ABS_PATH_RE.findall(command)
    write_paths = [m.strip("'\"") for m in _REDIRECT_RE.findall(command)]
    return read_paths, write_paths


# ── Main guard ──────────────────────────────────────────────

class ToolGuard:
    _PATH_ARGS: dict[str, tuple[str, ...]] = {
        "read_file": ("path", "file_path"),
        "write_file": ("path", "file_path"),
        "edit_file": ("path", "file_path"),
        "grep": ("path",),
        "glob_files": ("path",),
        "list_dir": ("path",),
        "git_ops": ("cwd", "path"),
        "shell": ("cwd",),
    }
    _LIST_PATH_ARGS: dict[str, tuple[str, ...]] = {
        "git_ops": ("files",),
    }
    _WRITE_TOOLS = frozenset({"write_file", "edit_file"})
    _FILE_TOOLS = frozenset(_PATH_ARGS) | frozenset(_LIST_PATH_ARGS)

    def __init__(self, rules_path: Path, allowed_dirs: list[Path] | None = None) -> None:
        self._rules: list[dict] = []
        if rules_path.is_file():
            self._rules = json.loads(rules_path.read_text(encoding="utf-8"))
        self.file_guard = FileGuard(allowed_dirs)
        self.audit = AuditLog()
        self.whitelist = SessionWhitelist()

    def _check_file_paths(self, tool_call: ToolCall) -> GuardResult | None:
        if tool_call.name not in self._FILE_TOOLS:
            return None

        is_write = tool_call.name in self._WRITE_TOOLS
        paths_to_check: list[tuple[str, bool]] = []

        for arg_name in self._PATH_ARGS.get(tool_call.name, ()):
            path_val = tool_call.arguments.get(arg_name)
            if path_val:
                paths_to_check.append((str(path_val), is_write))

        cwd_val = tool_call.arguments.get("cwd")
        cwd = str(cwd_val) if cwd_val else ""

        for arg_name in self._LIST_PATH_ARGS.get(tool_call.name, ()):
            raw_values = tool_call.arguments.get(arg_name) or []
            if not isinstance(raw_values, list):
                continue
            for raw in raw_values:
                p = Path(str(raw))
                if cwd and not p.is_absolute():
                    p = Path(cwd) / p
                paths_to_check.append((str(p), is_write))

        if tool_call.name == "shell":
            cmd = tool_call.arguments.get("command", "")
            read_paths, write_paths = _extract_shell_paths(cmd)
            for rp in read_paths:
                paths_to_check.append((rp, False))
            for wp in write_paths:
                paths_to_check.append((wp, True))

        for p, writing in paths_to_check:
            # Always enforce sensitive-path blocks — whitelist cannot bypass these
            result = self.file_guard.check_path(p, writing=writing)
            if not result.allowed:
                if self.whitelist.is_path_allowed(p) and result.needs_confirmation:
                    # Whitelisted path hit a soft block (e.g. .env write) — still block
                    pass
                return result
        return None

    def check(self, tool_call: ToolCall) -> GuardResult:
        level = TOOL_PERMISSIONS.get(tool_call.name, PermissionLevel.EXECUTE)

        if self.whitelist.is_tool_allowed(tool_call.name):
            result = GuardResult(allowed=True, level=level)
            self.audit.record(tool_call.name, tool_call.arguments, result, whitelisted=True)
            return result

        file_result = self._check_file_paths(tool_call)
        if file_result is not None:
            file_result.level = level
            self.audit.record(tool_call.name, tool_call.arguments, file_result)
            return file_result

        args_str = json.dumps(tool_call.arguments)
        for rule in self._rules:
            scoped_tools = rule.get("tools")
            if scoped_tools and tool_call.name not in scoped_tools:
                continue

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
                excluded = any(ep and re.search(ep, args_str) for ep in exclude_patterns)
                if excluded:
                    continue
                reason = rule.get("reason") or rule.get("description") or f"Blocked: {pattern}"
                result = GuardResult(
                    allowed=False,
                    reason=f"[{rule.get('id', '?')}] {reason}",
                    level=PermissionLevel.DESTRUCTIVE,
                )
                self.audit.record(tool_call.name, tool_call.arguments, result, rule_id=rule.get("id"))
                return result

        result = GuardResult(allowed=True, level=level)
        self.audit.record(tool_call.name, tool_call.arguments, result)
        return result

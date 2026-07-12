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

from engine.tool.interface import ToolCall, ToolDefinition


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
    "websearch": PermissionLevel.READ,
    "webfetch": PermissionLevel.READ,
    "memory_ops": PermissionLevel.WRITE,
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
    # True when the only problem is that the path sits outside the allowed
    # directories — the one block a session whitelist may override.  Sensitive
    # blocks (.ssh, .env writes, .git, …) keep this False and are never
    # bypassable.
    boundary_block: bool = False


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

        return GuardResult(
            allowed=False,
            reason=f"Path {path_str} outside allowed directories",
            boundary_block=True,
        )


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


def _rule_match_targets(arguments: dict) -> list[str]:
    """Strings that dangerous-command rule patterns are matched against.

    The JSON dump alone breaks ``$``-anchored patterns (every value in the
    dump is followed by ``"``), so each raw string value is matched as well.
    """
    targets: list[str] = [json.dumps(arguments, ensure_ascii=False)]
    stack: list[object] = list(arguments.values())
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
        elif isinstance(current, str):
            targets.append(current)
    return targets


# ── Main guard ──────────────────────────────────────────────

class ToolGuard:
    # Fallback lookup tables — used when a tool has no security metadata on its
    # ToolDefinition.  New tools should declare metadata instead of adding rows.
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

    def __init__(
        self,
        rules_path: Path,
        allowed_dirs: list[Path] | None = None,
        *,
        tool_registry: dict[str, ToolDefinition] | None = None,
    ) -> None:
        self._rules: list[dict] = []
        if rules_path.is_file():
            self._rules = json.loads(rules_path.read_text(encoding="utf-8"))
        self.file_guard = FileGuard(allowed_dirs)
        self.audit = AuditLog()
        self.whitelist = SessionWhitelist()
        self._tool_registry: dict[str, ToolDefinition] = tool_registry or {}

    def bind_definitions(self, definitions: dict[str, ToolDefinition]) -> None:
        """Bind tool definitions after registry load so metadata-first checks apply."""
        self._tool_registry = definitions

    def _resolve_path_metadata(self, tool_name: str) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
        """Return (path_args, list_path_args, is_write) for *tool_name*.

        Checks tool-declared metadata first, falls back to the hardcoded
        tables for tools that haven't declared their own metadata yet.
        """
        defn = self._tool_registry.get(tool_name)
        if defn is not None and (defn.path_args or defn.list_path_args):
            return defn.path_args, defn.list_path_args, defn.is_write_tool

        path_args = self._PATH_ARGS.get(tool_name, ())
        list_path_args = self._LIST_PATH_ARGS.get(tool_name, ())
        is_write = tool_name in self._WRITE_TOOLS
        return path_args, list_path_args, is_write

    def _check_file_paths(self, tool_call: ToolCall) -> GuardResult | None:
        path_args, list_path_args, is_write = self._resolve_path_metadata(tool_call.name)
        if not path_args and not list_path_args and tool_call.name != "shell":
            return None

        paths_to_check: list[tuple[str, bool]] = []

        for arg_name in path_args:
            path_val = tool_call.arguments.get(arg_name)
            if path_val:
                paths_to_check.append((str(path_val), is_write))

        cwd_val = tool_call.arguments.get("cwd")
        cwd = str(cwd_val) if cwd_val else ""

        for arg_name in list_path_args:
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
            result = self.file_guard.check_path(p, writing=writing)
            if not result.allowed:
                # The session whitelist may extend the directory boundary, but
                # it never bypasses sensitive-path blocks (.ssh, .env writes,
                # .git, …) — those return boundary_block=False.
                if result.boundary_block and self.whitelist.is_path_allowed(p):
                    continue
                return result
        return None

    def _resolve_permission_level(self, tool_name: str) -> PermissionLevel:
        """Return the permission level for *tool_name*.

        Tool-declared metadata wins; falls back to ``TOOL_PERMISSIONS``.
        """
        defn = self._tool_registry.get(tool_name)
        if defn is not None and defn.permission_level:
            try:
                return PermissionLevel(defn.permission_level)
            except ValueError:
                pass
        return TOOL_PERMISSIONS.get(tool_name, PermissionLevel.EXECUTE)

    def check(self, tool_call: ToolCall) -> GuardResult:
        level = self._resolve_permission_level(tool_call.name)

        if self.whitelist.is_tool_allowed(tool_call.name):
            result = GuardResult(allowed=True, level=level)
            self.audit.record(tool_call.name, tool_call.arguments, result, whitelisted=True)
            return result

        file_result = self._check_file_paths(tool_call)
        if file_result is not None:
            file_result.level = level
            self.audit.record(tool_call.name, tool_call.arguments, file_result)
            return file_result

        match_targets = _rule_match_targets(tool_call.arguments)
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
                for target in match_targets:
                    if not re.search(pattern, target):
                        continue
                    if any(ep and re.search(ep, target) for ep in exclude_patterns):
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

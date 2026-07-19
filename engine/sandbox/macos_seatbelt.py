"""macOS Seatbelt adapter for sandboxed tool execution."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .host import CommandResult, LocalExecutionEnvironment

_SANDBOX_EXECUTABLE = "/usr/bin/sandbox-exec"
_OPTIONAL_ENV_KEYS = ("LANG", "LC_ALL", "TERM", "TZ", "NO_COLOR")


def _sbpl_string(value: Path) -> str:
    """Encode a filesystem path as an SBPL string literal."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


class MacOSSeatbeltEnvironment:
    """Run commands under a deny-by-default Seatbelt profile.

    The workspace is the only writable location.  Network access is omitted
    from the profile and therefore denied.  This backend fails closed on a
    non-macOS host or when ``sandbox-exec`` is unavailable.
    """

    name = "sandbox"

    def __init__(self, *, workspace: str | Path) -> None:
        self._workspace = Path(workspace).expanduser().resolve()
        self._host = LocalExecutionEnvironment()

    def _profile(self) -> str:
        workspace = _sbpl_string(self._workspace)
        # ``system.sb`` supplies the narrow macOS runtime grants needed by
        # dynamically linked command-line programs.  The enclosing default
        # deny still blocks arbitrary files, writes, and networking; the
        # workspace grants below are the only project-data exception.
        return f'''(version 1)
(deny default)
(import "system.sb")
(deny network*)
(allow process*)
(allow file-read* (literal "/private/var/select/sh"))
(allow file-read* (subpath "/Applications/Xcode.app"))
(allow file-read* (subpath "/Library/Developer"))
(allow file-read* (literal "/private/var/db/xcode_select_link"))
(allow file-read-metadata (path-ancestors "{workspace}"))
(allow file-read* (subpath "{workspace}"))
(allow file-write* (subpath "{workspace}"))
'''

    def _validate_cwd(self, cwd: str | None) -> tuple[str | None, str | None]:
        resolved = Path(cwd).expanduser().resolve() if cwd else self._workspace
        try:
            resolved.relative_to(self._workspace)
        except ValueError:
            return None, f"sandbox working directory escapes workspace: {resolved}"
        return str(resolved), None

    def _safe_environment(self, requested: dict[str, str] | None) -> dict[str, str]:
        """Build the complete child environment; never inherit server secrets."""
        environment = {
            "PATH": os.defpath,
            "HOME": str(self._workspace),
            "TMPDIR": str(self._workspace),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "PIP_CONFIG_FILE": os.devnull,
            "NPM_CONFIG_USERCONFIG": os.devnull,
        }
        if requested:
            for key in _OPTIONAL_ENV_KEYS:
                value = requested.get(key)
                if value:
                    environment[key] = value
        return environment

    async def run_command(
        self,
        command: str | None = None,
        *,
        argv: list[str] | None = None,
        cwd: str | None = None,
        timeout_seconds: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        if sys.platform != "darwin":
            return CommandResult(exit_code=None, error="macOS Seatbelt is unavailable on this platform")
        if not os.path.isfile(_SANDBOX_EXECUTABLE) or not os.access(_SANDBOX_EXECUTABLE, os.X_OK):
            return CommandResult(exit_code=None, error="macOS sandbox-exec is unavailable")
        if (command is None) == (argv is None):
            return CommandResult(exit_code=None, error="exactly one of command or argv is required")
        resolved_cwd, error = self._validate_cwd(cwd)
        if error:
            return CommandResult(exit_code=None, error=error)

        wrapped_argv = [_SANDBOX_EXECUTABLE, "-p", self._profile()]
        if command is not None:
            wrapped_argv.extend(["/bin/sh", "-lc", command])
        else:
            assert argv is not None
            wrapped_argv.extend(argv)
        return await self._host.run_command(
            argv=wrapped_argv,
            cwd=resolved_cwd,
            timeout_seconds=timeout_seconds,
            env=self._safe_environment(env),
        )

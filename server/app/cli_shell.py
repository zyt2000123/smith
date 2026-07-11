from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Sequence

SHELL_ALIASES = {"shell", "ui"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _shell_entry_path() -> Path:
    return _repo_root() / "shell" / "dist" / "index.js"


def _normalize_argv(argv: Sequence[str] | None = None) -> list[str]:
    return list(argv) if argv is not None else sys.argv[1:]


def _extract_shell_argv(argv: Sequence[str] | None = None) -> list[str] | None:
    args = _normalize_argv(argv)
    if not args:
        return []
    if args[0] in SHELL_ALIASES:
        return args[1:]
    return None


def _should_launch_shell(
    argv: Sequence[str] | None = None,
    *,
    stdin_tty: bool | None = None,
    stdout_tty: bool | None = None,
) -> bool:
    shell_args = _extract_shell_argv(argv)
    if shell_args is None:
        return False

    input_is_tty = sys.stdin.isatty() if stdin_tty is None else stdin_tty
    output_is_tty = sys.stdout.isatty() if stdout_tty is None else stdout_tty
    return input_is_tty and output_is_tty


def _launch_shell(argv: Sequence[str] | None = None) -> int:
    entry = _shell_entry_path()
    if not entry.is_file():
        raise RuntimeError(
            "Smith terminal shell is not built yet. Run "
            f"`cd {_repo_root() / 'shell'} && npm install && npm run build` first."
        )

    shell_args = _extract_shell_argv(argv) or []
    command = ["node", str(entry), *shell_args]
    completed = subprocess.run(command, cwd=_repo_root(), check=False)
    return int(completed.returncode)

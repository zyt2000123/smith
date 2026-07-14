"""Shell command tool provider — executes commands with timeout and output limits."""

from __future__ import annotations

import asyncio
import os
import signal

TOOL_META = {
    "name": "shell",
    "description": (
        "Execute a host shell command from the project directory. Every command requires "
        "user approval and receives a minimal, credential-free environment."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 30, max 120)",
                "default": 30
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for command execution"
            }
        },
        "required": ["command"]
    },
    "path_args": ["cwd"],
    "permission_level": "execute",
    "approval_policy": "always",
    "side_effect": "external",
    "idempotent": False,
}

MAX_OUTPUT = 10 * 1024  # 10KB
MAX_TIMEOUT = 120
_STREAM_CHUNK_SIZE = 4096
_OUTPUT_DRAIN_TIMEOUT = 1.0
_TERMINATION_GRACE_SECONDS = 1.0
_SAFE_ENV_KEYS = ("LANG", "LC_ALL", "TERM", "TZ", "NO_COLOR")


def _safe_environment(cwd: str | None) -> dict[str, str]:
    """Return the minimal environment a model-requested shell may inherit.

    Provider credentials and other service secrets must never be exposed to a
    command string.  Pointing ``HOME`` at the project also prevents accidental
    reads of user-level config and credential files through shell expansion.
    """
    home = os.path.abspath(cwd) if cwd else os.getcwd()
    environment = {
        "PATH": os.environ.get("PATH") or os.defpath,
        "HOME": home,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "PIP_CONFIG_FILE": os.devnull,
        "NPM_CONFIG_USERCONFIG": os.devnull,
    }
    for key in _SAFE_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            environment[key] = value
    return environment


async def _read_limited(stream: asyncio.StreamReader) -> tuple[bytes, int]:
    """Drain a pipe without retaining more than ``MAX_OUTPUT`` bytes."""
    chunks: list[bytes] = []
    retained = 0
    total = 0
    while chunk := await stream.read(_STREAM_CHUNK_SIZE):
        total += len(chunk)
        remaining = MAX_OUTPUT - retained
        if remaining > 0:
            kept = chunk[:remaining]
            chunks.append(kept)
            retained += len(kept)
    return b"".join(chunks), total


def _format_stream(data: bytes, total: int) -> str:
    text = data.decode("utf-8", errors="replace")
    if total > len(data):
        return text + f"\n... (truncated, {total} bytes total)"
    return text


def _signal_process_group(proc: asyncio.subprocess.Process, sig: int) -> None:
    """Signal the full shell process group when the platform supports it."""
    try:
        if os.name == "posix":
            os.killpg(proc.pid, sig)
        elif sig == signal.SIGKILL:
            proc.kill()
        else:
            proc.terminate()
    except ProcessLookupError:
        pass


async def _stop_process_group(proc: asyncio.subprocess.Process) -> None:
    """Terminate a timed-out command and any children it left running."""
    _signal_process_group(proc, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), timeout=_TERMINATION_GRACE_SECONDS)
    except asyncio.TimeoutError:
        _signal_process_group(proc, signal.SIGKILL)
        await proc.wait()


async def _drain_streams(
    proc: asyncio.subprocess.Process,
    stdout_task: asyncio.Task[tuple[bytes, int]],
    stderr_task: asyncio.Task[tuple[bytes, int]],
) -> tuple[tuple[bytes, int], tuple[bytes, int]]:
    """Finish draining output, stopping background descendants if they hold pipes."""
    drain_task = asyncio.gather(stdout_task, stderr_task)
    try:
        return await asyncio.wait_for(
            asyncio.shield(drain_task), timeout=_OUTPUT_DRAIN_TIMEOUT
        )
    except asyncio.TimeoutError:
        _signal_process_group(proc, signal.SIGTERM)
        try:
            return await asyncio.wait_for(
                asyncio.shield(drain_task), timeout=_TERMINATION_GRACE_SECONDS
            )
        except asyncio.TimeoutError:
            _signal_process_group(proc, signal.SIGKILL)
            return await drain_task


async def _cancel_stream_tasks(
    stdout_task: asyncio.Task[tuple[bytes, int]] | None,
    stderr_task: asyncio.Task[tuple[bytes, int]] | None,
) -> None:
    tasks = [task for task in (stdout_task, stderr_task) if task is not None]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def execute(
    *, command: str, timeout: int = 30, cwd: str | None = None
) -> str:
    timeout = min(max(1, timeout), MAX_TIMEOUT)

    if cwd and not os.path.isdir(cwd):
        return f"Error: working directory does not exist: {cwd}"

    proc: asyncio.subprocess.Process | None = None
    stdout_task: asyncio.Task[tuple[bytes, int]] | None = None
    stderr_task: asyncio.Task[tuple[bytes, int]] | None = None
    try:
        process_options: dict[str, object] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": cwd,
            "env": _safe_environment(cwd),
        }
        if os.name == "posix":
            process_options["start_new_session"] = True
        proc = await asyncio.create_subprocess_shell(
            command,
            **process_options,
        )
        assert proc.stdout is not None and proc.stderr is not None
        stdout_task = asyncio.create_task(_read_limited(proc.stdout))
        stderr_task = asyncio.create_task(_read_limited(proc.stderr))
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        if proc is not None:
            await _stop_process_group(proc)
        await _cancel_stream_tasks(stdout_task, stderr_task)
        return f"Error: command timed out after {timeout}s"
    except asyncio.CancelledError:
        if proc is not None and proc.returncode is None:
            await _stop_process_group(proc)
        await _cancel_stream_tasks(stdout_task, stderr_task)
        raise
    except Exception as e:
        if proc is not None and proc.returncode is None:
            await _stop_process_group(proc)
        await _cancel_stream_tasks(stdout_task, stderr_task)
        return f"Error executing command: {e}"

    output_parts = []
    assert proc is not None and stdout_task is not None and stderr_task is not None
    (stdout, stdout_total), (stderr, stderr_total) = await _drain_streams(
        proc, stdout_task, stderr_task
    )

    stdout_text = _format_stream(stdout, stdout_total) if stdout else ""
    stderr_text = _format_stream(stderr, stderr_total) if stderr else ""

    if stdout_text:
        output_parts.append(stdout_text)

    if stderr_text:
        output_parts.append(f"[stderr]\n{stderr_text}")

    exit_code = proc.returncode
    result = "\n".join(output_parts) if output_parts else "(no output)"
    return f"[exit_code={exit_code}]\n{result}"

"""Execution environments — the only place tool commands become OS processes.

Layering contract: ``ToolPolicy`` decides whether a call may run, the
approval broker pauses for consent, and an :class:`ExecutionEnvironment`
actually executes. Tool providers receive the bound environment as an
injected ``environment`` keyword argument (duck-typed, so the content layer
never imports engine code) and must not spawn processes themselves.

Process-handling details (minimal env, process-group termination, output
capping) were moved here verbatim from ``agents/tools/shell.py``.
"""

from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

MAX_OUTPUT = 10 * 1024  # 10KB
_STREAM_CHUNK_SIZE = 4096
_OUTPUT_DRAIN_TIMEOUT = 1.0
_TERMINATION_GRACE_SECONDS = 1.0


@dataclass
class CommandResult:
    """Outcome of one command executed inside an environment."""

    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error: str | None = None


@runtime_checkable
class ExecutionEnvironment(Protocol):
    """Small, deep boundary for running side-effecting tool commands.

    Implementations own the full process lifecycle: spawn, timeout,
    cancellation, output capping, and cleanup.  ``name`` is matched against
    a tool's declared ``execution_environment`` ("host" / "sandbox").
    """

    name: str

    async def run_command(
        self,
        command: str | None = None,
        *,
        argv: list[str] | None = None,
        cwd: str | None = None,
        timeout_seconds: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> CommandResult: ...


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
    """Signal the full process group when the platform supports it."""
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


class LocalExecutionEnvironment:
    """Runs commands directly on the host with hardened process handling."""

    name = "host"

    async def run_command(
        self,
        command: str | None = None,
        *,
        argv: list[str] | None = None,
        cwd: str | None = None,
        timeout_seconds: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        if (command is None) == (argv is None):
            return CommandResult(
                exit_code=None,
                error="exactly one of command or argv is required",
            )

        proc: asyncio.subprocess.Process | None = None
        stdout_task: asyncio.Task[tuple[bytes, int]] | None = None
        stderr_task: asyncio.Task[tuple[bytes, int]] | None = None
        try:
            process_options: dict[str, object] = {
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
                "cwd": cwd,
                "env": env,
            }
            if os.name == "posix":
                process_options["start_new_session"] = True
            if command is not None:
                proc = await asyncio.create_subprocess_shell(command, **process_options)
            else:
                assert argv is not None
                proc = await asyncio.create_subprocess_exec(*argv, **process_options)
            assert proc.stdout is not None and proc.stderr is not None
            stdout_task = asyncio.create_task(_read_limited(proc.stdout))
            stderr_task = asyncio.create_task(_read_limited(proc.stderr))
            await asyncio.wait_for(proc.wait(), timeout=timeout_seconds)
        except FileNotFoundError:
            binary = argv[0] if argv else str(command)
            return CommandResult(
                exit_code=None,
                error=f"{binary} is not installed or not in PATH",
            )
        except asyncio.TimeoutError:
            if proc is not None:
                await _stop_process_group(proc)
            await _cancel_stream_tasks(stdout_task, stderr_task)
            return CommandResult(exit_code=None, timed_out=True)
        except asyncio.CancelledError:
            if proc is not None and proc.returncode is None:
                await _stop_process_group(proc)
            await _cancel_stream_tasks(stdout_task, stderr_task)
            raise
        except Exception as e:
            if proc is not None and proc.returncode is None:
                await _stop_process_group(proc)
            await _cancel_stream_tasks(stdout_task, stderr_task)
            return CommandResult(exit_code=None, error=str(e))

        assert stdout_task is not None and stderr_task is not None
        (stdout, stdout_total), (stderr, stderr_total) = await _drain_streams(
            proc, stdout_task, stderr_task
        )
        return CommandResult(
            exit_code=proc.returncode,
            stdout=_format_stream(stdout, stdout_total) if stdout else "",
            stderr=_format_stream(stderr, stderr_total) if stderr else "",
        )

"""Tests for the execution environment boundary.

Covers the LocalExecutionEnvironment process lifecycle (spawn, timeout,
cancellation, output capping, environment failures) and the registry's
environment binding: injection into tool providers and rejection of tools
whose declared environment is unavailable. The process-group tests were
migrated from test_shell_safety.py when process handling moved out of the
shell provider.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from engine.tool import environment as environment_module
from engine.tool.environment import (
    MAX_OUTPUT,
    CommandResult,
    ExecutionEnvironment,
    LocalExecutionEnvironment,
)
from engine.tool.interface import ToolCall
from engine.tool.registry import ToolRegistry

ROOT = Path(__file__).resolve().parents[2]


class _PipeReader:
    def __init__(self, chunks: list[bytes] | None = None) -> None:
        self._chunks = chunks or []

    async def read(self, _: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""


def test_local_environment_satisfies_the_protocol() -> None:
    assert isinstance(LocalExecutionEnvironment(), ExecutionEnvironment)


def test_local_environment_runs_shell_commands() -> None:
    result = asyncio.run(LocalExecutionEnvironment().run_command("printf hello"))

    assert result.exit_code == 0
    assert result.stdout == "hello"
    assert not result.timed_out
    assert result.error is None


def test_local_environment_runs_argv_without_shell_interpretation() -> None:
    result = asyncio.run(
        LocalExecutionEnvironment().run_command(argv=["printf", "%s", "$HOME"])
    )

    assert result.exit_code == 0
    assert result.stdout == "$HOME"


def test_local_environment_requires_exactly_one_command_form() -> None:
    env = LocalExecutionEnvironment()

    both = asyncio.run(env.run_command("echo hi", argv=["echo", "hi"]))
    neither = asyncio.run(env.run_command())

    assert both.error and neither.error


def test_local_environment_reports_missing_binaries() -> None:
    result = asyncio.run(
        LocalExecutionEnvironment().run_command(argv=["definitely-not-a-binary-4242"])
    )

    assert result.exit_code is None
    assert result.error == "definitely-not-a-binary-4242 is not installed or not in PATH"


def test_local_environment_times_out_and_reports_it() -> None:
    started = time.monotonic()
    result = asyncio.run(
        LocalExecutionEnvironment().run_command("sleep 30", timeout_seconds=0.2)
    )

    assert result.timed_out
    assert result.exit_code is None
    assert time.monotonic() - started < 10


def test_local_environment_caps_stream_output() -> None:
    overflow = MAX_OUTPUT + 64
    result = asyncio.run(
        LocalExecutionEnvironment().run_command(
            argv=[sys.executable, "-c", f"print('x' * {overflow}, end='')"]
        )
    )

    assert result.exit_code == 0
    assert result.stdout.startswith("x" * MAX_OUTPUT)
    assert f"(truncated, {overflow} bytes total)" in result.stdout


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-specific")
def test_local_environment_timeout_terminates_the_entire_process_group(monkeypatch) -> None:
    signals: list[tuple[int, int]] = []

    async def scenario() -> CommandResult:
        terminated = asyncio.Event()

        class Process:
            pid = 12345
            returncode: int | None = None
            stdout = _PipeReader()
            stderr = _PipeReader()

            async def wait(self) -> int:
                if self.returncode is None:
                    await terminated.wait()
                assert self.returncode is not None
                return self.returncode

        process = Process()

        async def create_process(*_: object, **__: object) -> Process:
            return process

        def killpg(pid: int, sig: int) -> None:
            signals.append((pid, sig))
            process.returncode = -sig
            terminated.set()

        monkeypatch.setattr(
            environment_module.asyncio, "create_subprocess_shell", create_process
        )
        monkeypatch.setattr(environment_module.os, "killpg", killpg)
        return await LocalExecutionEnvironment().run_command(
            "long-running", timeout_seconds=1
        )

    result = asyncio.run(scenario())

    assert result.timed_out
    assert signals == [(12345, signal.SIGTERM)]


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-specific")
def test_local_environment_closes_background_children_that_hold_pipes(monkeypatch) -> None:
    signals: list[tuple[int, int]] = []

    async def scenario() -> CommandResult:
        close_pipes = asyncio.Event()

        class Reader:
            async def read(self, _: int) -> bytes:
                await close_pipes.wait()
                return b""

        class Process:
            pid = 24680
            returncode = 0
            stdout = Reader()
            stderr = Reader()

            async def wait(self) -> int:
                return self.returncode

        async def create_process(*_: object, **__: object) -> Process:
            return Process()

        def killpg(pid: int, sig: int) -> None:
            signals.append((pid, sig))
            close_pipes.set()

        monkeypatch.setattr(environment_module, "_OUTPUT_DRAIN_TIMEOUT", 0.01)
        monkeypatch.setattr(
            environment_module.asyncio, "create_subprocess_shell", create_process
        )
        monkeypatch.setattr(environment_module.os, "killpg", killpg)
        return await LocalExecutionEnvironment().run_command("background-child")

    result = asyncio.run(scenario())

    assert result.exit_code == 0
    assert result.stdout == "" and result.stderr == ""
    assert signals == [(24680, signal.SIGTERM)]


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-specific")
def test_local_environment_escalates_to_kill_for_a_stuck_process_group(monkeypatch) -> None:
    signals: list[tuple[int, int]] = []

    async def scenario() -> None:
        released = asyncio.Event()

        class Process:
            pid = 13579
            returncode: int | None = None

            async def wait(self) -> int:
                if self.returncode is None:
                    await released.wait()
                assert self.returncode is not None
                return self.returncode

        process = Process()

        def killpg(pid: int, sig: int) -> None:
            signals.append((pid, sig))
            if sig == signal.SIGKILL:
                process.returncode = -sig
                released.set()

        monkeypatch.setattr(environment_module, "_TERMINATION_GRACE_SECONDS", 0.01)
        monkeypatch.setattr(environment_module.os, "killpg", killpg)
        await environment_module._stop_process_group(process)

    asyncio.run(scenario())

    assert signals == [(13579, signal.SIGTERM), (13579, signal.SIGKILL)]


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-specific")
def test_local_environment_cancellation_terminates_the_process_group(monkeypatch) -> None:
    signals: list[tuple[int, int]] = []

    async def scenario() -> None:
        started = asyncio.Event()
        terminated = asyncio.Event()

        class Process:
            pid = 67890
            returncode: int | None = None
            stdout = _PipeReader()
            stderr = _PipeReader()

            async def wait(self) -> int:
                started.set()
                if self.returncode is None:
                    await terminated.wait()
                assert self.returncode is not None
                return self.returncode

        process = Process()

        async def create_process(*_: object, **__: object) -> Process:
            return process

        def killpg(pid: int, sig: int) -> None:
            signals.append((pid, sig))
            process.returncode = -sig
            terminated.set()

        monkeypatch.setattr(
            environment_module.asyncio, "create_subprocess_shell", create_process
        )
        monkeypatch.setattr(environment_module.os, "killpg", killpg)
        task = asyncio.create_task(
            LocalExecutionEnvironment().run_command("long-running")
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert signals == [(67890, signal.SIGTERM)]


def test_registry_injects_the_bound_environment() -> None:
    registry = ToolRegistry()

    async def probe(*, environment=None) -> str:
        return f"env={getattr(environment, 'name', None)}"

    registry.register(name="probe", description="", parameters={}, func=probe)

    result = asyncio.run(registry.execute(ToolCall(id="1", name="probe", arguments={})))

    assert result.content == "env=host"


def test_registry_injection_overrides_model_supplied_environment() -> None:
    registry = ToolRegistry()

    async def probe(*, environment=None) -> str:
        return f"env={getattr(environment, 'name', None)}"

    registry.register(name="probe", description="", parameters={}, func=probe)

    result = asyncio.run(
        registry.execute(
            ToolCall(id="1", name="probe", arguments={"environment": "forged"})
        )
    )

    assert result.content == "env=host"


def test_registry_blocks_tools_that_require_a_missing_sandbox() -> None:
    registry = ToolRegistry()
    calls: list[str] = []

    async def sandboxed() -> str:
        calls.append("ran")
        return "ran"

    registry.register(
        name="sandboxed",
        description="",
        parameters={},
        func=sandboxed,
        execution_environment="sandbox",
    )

    result = asyncio.run(
        registry.execute(ToolCall(id="1", name="sandboxed", arguments={}))
    )

    assert result.is_error
    assert result.error_kind == "environment_unavailable"
    assert calls == []


def test_registry_allows_either_tools_under_any_environment() -> None:
    class FakeSandbox:
        name = "sandbox"

        async def run_command(
            self, command=None, *, argv=None, cwd=None, timeout_seconds=30.0, env=None
        ) -> CommandResult:
            return CommandResult(exit_code=0, stdout="sandboxed")

    registry = ToolRegistry()

    async def probe(*, environment=None) -> str:
        return f"env={environment.name}"

    registry.register(
        name="probe",
        description="",
        parameters={},
        func=probe,
        execution_environment="either",
    )
    registry.bind_execution_environment(FakeSandbox())

    result = asyncio.run(registry.execute(ToolCall(id="1", name="probe", arguments={})))

    assert result.content == "env=sandbox"


def test_git_ops_runs_through_the_environment_end_to_end(tmp_path: Path) -> None:
    init = asyncio.run(
        LocalExecutionEnvironment().run_command(argv=["git", "init", str(tmp_path)])
    )
    assert init.exit_code == 0, init.error or init.stderr

    registry = ToolRegistry()
    registry.load_providers(ROOT / "agents" / "tools")

    result = asyncio.run(
        registry.execute(
            ToolCall(
                id="1",
                name="git_ops",
                arguments={"action": "status", "cwd": str(tmp_path)},
            )
        )
    )

    assert not result.is_error, result.content
    assert result.content.startswith("[exit_code=0]")

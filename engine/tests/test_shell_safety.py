"""Regression tests for the privileged raw-shell execution boundary."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import signal
from pathlib import Path

import pytest

from engine.safety.tool_guard import ToolGuard
from engine.tool.interface import ToolCall
from engine.tool.registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "agents" / "safety" / "dangerous_commands.json"
def _load_shell_provider():
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module("agents.tools.shell")


def test_raw_shell_always_requires_user_approval(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    guard = ToolGuard(RULES, allowed_dirs=[project])

    for command in (
        "cat ../outside.txt",
        "cat $PWD/../outside.txt",
        "echo $OPENAI_API_KEY",
        "printf ok | tee ../outside.txt",
    ):
        result = guard.check(
            ToolCall(
                id=command,
                name="shell",
                arguments={"command": command, "cwd": str(project)},
            )
        )
        assert result.allowed, command
        assert result.approval_required, command


def test_shell_definition_records_external_side_effects() -> None:
    registry = ToolRegistry()
    registry.load_providers(ROOT / "agents" / "tools")

    definition = registry.definitions()["shell"]
    assert definition.permission_level == "execute"
    assert definition.approval_policy == "always"
    assert definition.side_effect == "external"
    assert not definition.idempotent


def test_shell_strips_inherited_secrets_and_caps_streamed_output(
    monkeypatch, tmp_path: Path
) -> None:
    shell = _load_shell_provider()
    captured: dict[str, object] = {}

    class Reader:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = chunks

        async def read(self, _: int) -> bytes:
            return self._chunks.pop(0) if self._chunks else b""

    class Process:
        pid = 12345
        returncode = 0
        stdout = Reader([b"x" * (shell.MAX_OUTPUT + 32)])
        stderr = Reader([])

        async def wait(self) -> int:
            return self.returncode

    async def create_process(command: str, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return Process()

    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setattr(shell.asyncio, "create_subprocess_shell", create_process)

    result = asyncio.run(shell.execute(command="echo ok", cwd=str(tmp_path)))

    environment = captured["env"]
    assert isinstance(environment, dict)
    assert "OPENAI_API_KEY" not in environment
    assert environment["HOME"] == str(tmp_path.resolve())
    assert captured["cwd"] == str(tmp_path)
    if os.name == "posix":
        assert captured["start_new_session"] is True
    assert "x" * shell.MAX_OUTPUT in result
    assert f"{shell.MAX_OUTPUT + 32} bytes total" in result


def test_shell_process_cannot_read_the_service_secret_environment(
    monkeypatch, tmp_path: Path
) -> None:
    shell = _load_shell_provider()
    monkeypatch.setenv("OPENAI_API_KEY", "shell-test-secret")

    result = asyncio.run(
        shell.execute(command='printf "%s" "$OPENAI_API_KEY"', cwd=str(tmp_path))
    )

    assert "shell-test-secret" not in result
    assert result == "[exit_code=0]\n(no output)"


def test_shell_preserves_small_stderr_and_rejects_missing_workdir(tmp_path: Path) -> None:
    shell = _load_shell_provider()

    stderr_result = asyncio.run(shell.execute(command="printf failure >&2", cwd=str(tmp_path)))
    missing_result = asyncio.run(shell.execute(command="pwd", cwd=str(tmp_path / "missing")))

    assert shell._format_stream(b"ok", 2) == "ok"
    assert stderr_result == "[exit_code=0]\n[stderr]\nfailure"
    assert missing_result == f"Error: working directory does not exist: {tmp_path / 'missing'}"


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-specific")
def test_shell_timeout_terminates_the_entire_process_group(monkeypatch, tmp_path: Path) -> None:
    shell = _load_shell_provider()
    signals: list[tuple[int, int]] = []

    class Reader:
        async def read(self, _: int) -> bytes:
            return b""

    async def run() -> tuple[str, object]:
        terminated = asyncio.Event()

        class Process:
            pid = 12345
            returncode: int | None = None
            stdout = Reader()
            stderr = Reader()

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

        monkeypatch.setattr(shell.asyncio, "create_subprocess_shell", create_process)
        monkeypatch.setattr(shell.os, "killpg", killpg)
        result = await shell.execute(command="long-running", timeout=1, cwd=str(tmp_path))
        return result, process

    result, _ = asyncio.run(run())

    assert result == "Error: command timed out after 1s"
    assert signals == [(12345, signal.SIGTERM)]


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-specific")
def test_shell_closes_background_children_that_hold_output_pipes(monkeypatch, tmp_path: Path) -> None:
    shell = _load_shell_provider()
    signals: list[tuple[int, int]] = []

    async def run() -> str:
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

        monkeypatch.setattr(shell, "_OUTPUT_DRAIN_TIMEOUT", 0.01)
        monkeypatch.setattr(shell.asyncio, "create_subprocess_shell", create_process)
        monkeypatch.setattr(shell.os, "killpg", killpg)
        return await shell.execute(command="background-child", cwd=str(tmp_path))

    assert asyncio.run(run()) == "[exit_code=0]\n(no output)"
    assert signals == [(24680, signal.SIGTERM)]


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-specific")
def test_shell_escalates_to_kill_for_a_stuck_process_group(monkeypatch) -> None:
    shell = _load_shell_provider()
    signals: list[tuple[int, int]] = []

    async def run() -> None:
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

        monkeypatch.setattr(shell, "_TERMINATION_GRACE_SECONDS", 0.01)
        monkeypatch.setattr(shell.os, "killpg", killpg)
        await shell._stop_process_group(process)

    asyncio.run(run())

    assert signals == [(13579, signal.SIGTERM), (13579, signal.SIGKILL)]


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-specific")
def test_shell_cancellation_terminates_the_process_group(monkeypatch, tmp_path: Path) -> None:
    shell = _load_shell_provider()
    signals: list[tuple[int, int]] = []

    class Reader:
        async def read(self, _: int) -> bytes:
            return b""

    async def run() -> None:
        started = asyncio.Event()
        terminated = asyncio.Event()

        class Process:
            pid = 67890
            returncode: int | None = None
            stdout = Reader()
            stderr = Reader()

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

        monkeypatch.setattr(shell.asyncio, "create_subprocess_shell", create_process)
        monkeypatch.setattr(shell.os, "killpg", killpg)
        task = asyncio.create_task(shell.execute(command="long-running", cwd=str(tmp_path)))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())

    assert signals == [(67890, signal.SIGTERM)]

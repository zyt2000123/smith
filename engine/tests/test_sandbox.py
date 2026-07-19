"""Contract tests for the engine-level sandbox execution boundary."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from engine.sandbox import (
    CommandResult,
    ExecutionEnvironment,
    LocalExecutionEnvironment,
    MacOSSeatbeltEnvironment,
)


def test_host_environment_remains_an_execution_environment() -> None:
    """Host execution remains a supported explicit backend."""
    assert isinstance(LocalExecutionEnvironment(), ExecutionEnvironment)


def test_macos_seatbelt_environment_is_a_sandbox_backend(tmp_path: Path) -> None:
    environment = MacOSSeatbeltEnvironment(workspace=tmp_path)

    assert isinstance(environment, ExecutionEnvironment)
    assert environment.name == "sandbox"
    assert "(deny network*)" in environment._profile()


def test_macos_seatbelt_rejects_a_working_directory_outside_the_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = asyncio.run(
        MacOSSeatbeltEnvironment(workspace=workspace).run_command(
            argv=["/bin/echo", "never-runs"], cwd=str(tmp_path)
        )
    )

    assert result.exit_code is None
    assert result.error and "escapes workspace" in result.error


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt is macOS-only")
def test_macos_seatbelt_does_not_inherit_parent_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMITH_TEST_SECRET", "must-not-leak")
    environment = MacOSSeatbeltEnvironment(workspace=tmp_path)

    result = asyncio.run(
        environment.run_command(argv=["/usr/bin/env"], cwd=str(tmp_path))
    )

    assert result.exit_code == 0, result.stderr or result.error
    assert "SMITH_TEST_SECRET" not in result.stdout
    assert f"HOME={tmp_path.resolve()}" in result.stdout
    assert "GIT_CONFIG_GLOBAL=/dev/null" in result.stdout


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt is macOS-only")
def test_macos_seatbelt_runs_in_workspace_and_blocks_writes_outside_it(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    protected_path = tmp_path / "outside.txt"
    environment = MacOSSeatbeltEnvironment(workspace=workspace)

    allowed = asyncio.run(
        environment.run_command(
            argv=["/bin/sh", "-c", "printf allowed > inside.txt"],
            cwd=str(workspace),
        )
    )
    blocked = asyncio.run(
        environment.run_command(
            argv=["/bin/sh", "-c", f"printf blocked > {protected_path}"],
            cwd=str(workspace),
        )
    )

    assert allowed == CommandResult(exit_code=0)
    assert (workspace / "inside.txt").read_text() == "allowed"
    assert blocked.exit_code != 0
    assert not protected_path.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt is macOS-only")
def test_macos_seatbelt_blocks_outbound_network(tmp_path: Path) -> None:
    result = asyncio.run(
        MacOSSeatbeltEnvironment(workspace=tmp_path).run_command(
            argv=["/usr/bin/curl", "--connect-timeout", "1", "https://example.com"],
            cwd=str(tmp_path),
            timeout_seconds=3,
        )
    )

    assert result.exit_code not in (None, 0)
    assert "Operation not permitted" in result.stderr

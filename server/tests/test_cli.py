from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cli import (  # noqa: E402
    _context_from_args,
    _extract_shell_argv,
    _find_session_in_list,
    _should_launch_shell,
    build_parser,
    ensure_smith,
    resolve_session,
)


class FakeAgentService:
    def __init__(self, sessions: list[SimpleNamespace] | None = None) -> None:
        self.get_profile_calls = 0
        self.sessions = sessions or []

    async def get_profile(self) -> SimpleNamespace:
        self.get_profile_calls += 1
        return SimpleNamespace(
            id="smith-id",
            name="Smith",
            role="personal-assistant",
            online=True,
            description="resident",
        )

    async def list_sessions(self) -> list[SimpleNamespace]:
        return list(self.sessions)


@pytest.mark.asyncio
async def test_ensure_smith_uses_the_single_agent_facade() -> None:
    service = FakeAgentService()

    profile = await ensure_smith(service)

    assert profile.id == "smith-id"
    assert service.get_profile_calls == 1


@pytest.mark.asyncio
async def test_resolve_session_uses_only_smith_sessions() -> None:
    service = FakeAgentService([
        SimpleNamespace(id="sess-001", title="First"),
        SimpleNamespace(id="sess-002", title="Second"),
    ])

    session = await resolve_session(service, "sess-002")

    assert session.title == "Second"


def test_chat_parser_has_no_agent_selector_and_accepts_identity() -> None:
    args = build_parser().parse_args([
        "chat",
        "--identity",
        "legal",
        "--message",
        "hello",
    ])

    assert not hasattr(args, "agent")
    assert args.identity == "legal"


def test_chat_parser_accepts_session_resume() -> None:
    args = build_parser().parse_args([
        "chat",
        "--session",
        "sess-123",
        "--message",
        "hello",
    ])

    assert args.session == "sess-123"
    assert args.identity is None


def test_extract_shell_argv_supports_default_and_alias() -> None:
    assert _extract_shell_argv([]) == []
    assert _extract_shell_argv(["shell", "--foo"]) == ["--foo"]
    assert _extract_shell_argv(["chat"]) is None


def test_should_launch_shell_requires_tty() -> None:
    assert _should_launch_shell([], stdin_tty=True, stdout_tty=True) is True
    assert _should_launch_shell(["shell"], stdin_tty=True, stdout_tty=True) is True
    assert _should_launch_shell([], stdin_tty=False, stdout_tty=True) is False
    assert _should_launch_shell(["chat"], stdin_tty=True, stdout_tty=True) is False


def test_find_session_in_list_matches_by_id() -> None:
    sessions = [
        SimpleNamespace(id="sess-001", title="First"),
        SimpleNamespace(id="sess-002", title="Second"),
    ]

    session = _find_session_in_list("sess-002", sessions)

    assert session is not None
    assert session.title == "Second"


def test_context_from_args_combines_workdir_and_context() -> None:
    args = SimpleNamespace(
        workdir=".",
        context="Focus on reproducible output.",
    )

    context = _context_from_args(args)

    assert context is not None
    assert f"Working directory: {Path('.').resolve()}" in context
    assert "Focus on reproducible output." in context

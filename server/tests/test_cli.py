from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cli import (
    BUILTIN_AGENT,
    _context_from_args,
    _find_session_in_list,
    build_parser,
    ensure_builtin_agent,
    resolve_agent,
)


class FakeEmployeeService:
    def __init__(self, employees: list[SimpleNamespace]) -> None:
        self.employees = employees
        self.create_calls = 0

    async def list_employees(self) -> list[SimpleNamespace]:
        return list(self.employees)

    async def create_employee(self, body) -> SimpleNamespace:
        self.create_calls += 1
        employee = SimpleNamespace(
            id=f"emp-{self.create_calls}",
            name=body.name,
            role=body.role,
            online=True,
            description=body.description,
        )
        self.employees.append(employee)
        return employee


@pytest.mark.asyncio
async def test_ensure_builtin_agent_is_idempotent() -> None:
    svc = FakeEmployeeService([
        SimpleNamespace(
            id="existing-smith",
            name="Smith",
            role="personal-assistant",
            online=True,
            description="existing",
        )
    ])

    first = await ensure_builtin_agent(svc)
    second = await ensure_builtin_agent(svc)

    assert first.id == "existing-smith"
    assert second.id == "existing-smith"
    assert svc.create_calls == 0
    assert sorted(employee.name for employee in svc.employees) == ["Smith"]


@pytest.mark.asyncio
async def test_resolve_agent_prefers_builtin_alias_target() -> None:
    svc = FakeEmployeeService([
        SimpleNamespace(
            id="custom-assistant",
            name="Custom",
            role="personal-assistant",
            online=True,
            description="custom",
        ),
        SimpleNamespace(
            id="smith-id",
            name="Smith",
            role="personal-assistant",
            online=True,
            description="demo",
        ),
    ])

    employee = await resolve_agent(svc, "assistant", ensure_builtin=False)

    assert employee.id == "smith-id"


def test_chat_parser_defaults_to_builtin_agent() -> None:
    args = build_parser().parse_args(["chat", "--message", "hello"])

    assert args.agent == BUILTIN_AGENT.key
    assert args.no_ensure_agent is False


def test_chat_parser_accepts_session_resume() -> None:
    args = build_parser().parse_args([
        "chat",
        "--session",
        "sess-123",
        "--message",
        "hello",
    ])

    assert args.agent == BUILTIN_AGENT.key
    assert args.session == "sess-123"


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

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence


def _bootstrap_repo_paths() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    for path in (root / "common", root / "engine", root):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


_bootstrap_repo_paths()


from common.config import TEMPLATES_DIR  # noqa: E402


@dataclass(frozen=True)
class BuiltInAgentSpec:
    key: str
    name: str
    role: str
    description: str
    aliases: tuple[str, ...]


BUILTIN_AGENT = BuiltInAgentSpec(
    key="assistant",
    name="Smith",
    role="personal-assistant",
    description=(
        "面向个人工作流的常驻本地 Agent，负责理解目标、整理上下文、检索信息、"
        "规划执行并交付可落地结果。"
    ),
    aliases=("smith", "assistant", "agent", "default", "pa", "personal-assistant"),
)


class EmployeeServiceLike(Protocol):
    async def list_employees(self) -> list[Any]:
        ...

    async def create_employee(self, body: Any) -> Any:
        ...


class SessionServiceLike(Protocol):
    async def list_sessions(self, employee_id: str) -> list[Any]:
        ...

    async def create_session(self, employee_id: str, title: str) -> Any:
        ...

    async def list_messages(
        self,
        session_id: str,
        limit: int = 0,
        offset: int = 0,
    ) -> list[Any]:
        ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-smith-cli",
        description="Developer CLI for the built-in Agent-Smith personal assistant.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    agent_parser = subparsers.add_parser(
        "agent",
        help="Manage the built-in personal assistant agent.",
    )
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command", required=True)
    agent_ensure = agent_subparsers.add_parser(
        "ensure",
        help="Create the built-in personal assistant agent if it does not exist yet.",
    )
    agent_ensure.set_defaults(handler=cmd_agent_ensure)

    agent_show = agent_subparsers.add_parser(
        "show",
        help="Show the built-in personal assistant agent.",
    )
    agent_show.add_argument(
        "--ensure",
        action="store_true",
        help="Create the built-in personal assistant agent before showing it.",
    )
    agent_show.set_defaults(handler=cmd_agent_show)

    demo_parser = subparsers.add_parser(
        "demo",
        help="Legacy compatibility commands.",
    )
    demo_subparsers = demo_parser.add_subparsers(dest="demo_command", required=True)
    demo_ensure = demo_subparsers.add_parser(
        "ensure",
        help="Legacy alias for `agent ensure`.",
    )
    demo_ensure.set_defaults(handler=cmd_agent_ensure)

    employees_parser = subparsers.add_parser(
        "employees",
        help="Inspect raw stored agent records.",
    )
    employees_subparsers = employees_parser.add_subparsers(dest="employees_command", required=True)
    employees_list = employees_subparsers.add_parser(
        "list",
        help="List all stored agent records.",
    )
    employees_list.add_argument(
        "--ensure-agent",
        "--ensure-demo",
        action="store_true",
        help="Create the built-in personal assistant agent before listing records.",
    )
    employees_list.set_defaults(handler=cmd_employees_list)

    sessions_parser = subparsers.add_parser(
        "sessions",
        help="Inspect conversation sessions for an agent.",
    )
    sessions_subparsers = sessions_parser.add_subparsers(
        dest="sessions_command",
        required=True,
    )
    sessions_list = sessions_subparsers.add_parser(
        "list",
        help="List sessions for an agent.",
    )
    sessions_list.add_argument(
        "agent",
        nargs="?",
        default=BUILTIN_AGENT.key,
        help="Agent id, name, or alias. Defaults to the built-in personal assistant.",
    )
    sessions_list.add_argument(
        "--ensure-agent",
        action="store_true",
        help="Create the built-in personal assistant before listing sessions.",
    )
    sessions_list.set_defaults(handler=cmd_sessions_list)

    sessions_show = sessions_subparsers.add_parser(
        "show",
        help="Show messages for one session.",
    )
    sessions_show.add_argument("session_id", help="Session id to inspect.")
    sessions_show.add_argument(
        "agent",
        nargs="?",
        default=BUILTIN_AGENT.key,
        help="Agent id, name, or alias. Defaults to the built-in personal assistant.",
    )
    sessions_show.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit the number of messages returned. Defaults to all.",
    )
    sessions_show.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip the first N messages before printing.",
    )
    sessions_show.add_argument(
        "--ensure-agent",
        action="store_true",
        help="Create the built-in personal assistant before resolving the agent.",
    )
    sessions_show.set_defaults(handler=cmd_sessions_show)

    chat_parser = subparsers.add_parser(
        "chat",
        help="Chat with the built-in personal assistant or another stored agent.",
    )
    chat_parser.add_argument(
        "agent",
        nargs="?",
        default=BUILTIN_AGENT.key,
        help="Agent id, name, or alias. Defaults to the built-in personal assistant.",
    )
    chat_parser.add_argument(
        "-m",
        "--message",
        help="Send a single message and exit. Without this flag, start an interactive REPL.",
    )
    chat_parser.add_argument(
        "--context",
        help="Implicit context injected into the engine but not persisted in chat history.",
    )
    chat_parser.add_argument(
        "--workdir",
        help="Convenience alias for context: inject the current task working directory.",
    )
    chat_parser.add_argument(
        "--session-title",
        default="CLI Chat",
        help="Title used when creating a new conversation session.",
    )
    chat_parser.add_argument(
        "--session",
        help="Continue an existing session id instead of creating a new session.",
    )
    chat_parser.add_argument(
        "--no-ensure-agent",
        "--no-ensure-demo",
        action="store_true",
        help="Do not auto-create the built-in personal assistant before resolving the selector.",
    )
    chat_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show skill/tool/thinking trace in addition to assistant text.",
    )
    chat_parser.set_defaults(handler=cmd_chat)

    return parser


def _normalize(value: str) -> str:
    return value.strip().lower()


def _find_builtin_agent_spec(selector: str) -> BuiltInAgentSpec | None:
    key = _normalize(selector)
    if key == BUILTIN_AGENT.key or key in BUILTIN_AGENT.aliases:
        return BUILTIN_AGENT
    return None


def _format_employee_line(employee: Any) -> str:
    role = getattr(employee, "role", "")
    status = "online" if getattr(employee, "online", False) else "offline"
    return f"{employee.id}  {employee.name}  role={role}  status={status}"


def _format_session_line(session: Any) -> str:
    message_count = getattr(session, "message_count", 0)
    updated_at = (
        getattr(session, "last_message_at", None)
        or getattr(session, "created_at", "")
    )
    return (
        f"{session.id}  {session.title}  messages={message_count}  "
        f"updated={updated_at}"
    )


def _print_employee_table(employees: Sequence[Any]) -> None:
    if not employees:
        print(
            "No agent records found. Run `agent ensure` to create the built-in "
            "personal assistant."
        )
        return
    for employee in employees:
        print(_format_employee_line(employee))


def _print_session_table(sessions: Sequence[Any]) -> None:
    if not sessions:
        print("No sessions found for this agent yet.")
        return
    for session in sessions:
        print(_format_session_line(session))
        preview = getattr(session, "last_message_preview", None)
        if preview:
            print(f"  preview: {preview}")


def _print_messages(messages: Sequence[Any]) -> None:
    if not messages:
        print("No messages found in this session.")
        return
    for message in messages:
        print(f"[{message.role}] {message.created_at}")
        print(message.content)
        print()


def _context_from_args(args: argparse.Namespace) -> str | None:
    parts: list[str] = []
    if args.workdir:
        workdir = Path(args.workdir).expanduser().resolve()
        parts.append(f"Working directory: {workdir}")
    if args.context:
        parts.append(args.context.strip())
    if not parts:
        return None
    return "\n\n".join(part for part in parts if part)


def _pick_initial_prompt(message: str) -> str:
    first_line = message.strip().splitlines()[0].strip()
    if not first_line:
        return "CLI Chat"
    return first_line[:40]


def _find_session_in_list(session_id: str, sessions: Sequence[Any]) -> Any | None:
    key = _normalize(session_id)
    for session in sessions:
        if _normalize(getattr(session, "id", "")) == key:
            return session
    return None


async def _build_employee_service() -> Any:
    from .infrastructure.repositories.employee_repo import EmployeeRepo
    from .services.employee_service import EmployeeService

    return EmployeeService(EmployeeRepo())


async def _build_session_service() -> Any:
    from .infrastructure.repositories.employee_repo import EmployeeRepo
    from .infrastructure.repositories.session_repo import SessionRepo
    from .services.session_service import SessionService

    return SessionService(SessionRepo(), EmployeeRepo())


async def ensure_builtin_agent(employee_service: EmployeeServiceLike) -> Any:
    from .domain.employee import EmployeeCreate

    existing = await employee_service.list_employees()
    by_name_role = {
        (_normalize(employee.name), _normalize(employee.role)): employee
        for employee in existing
    }

    spec = BUILTIN_AGENT
    match = by_name_role.get((_normalize(spec.name), _normalize(spec.role)))
    if match is not None:
        return match

    if not (TEMPLATES_DIR / spec.role).is_dir():
        raise RuntimeError(f"Missing template directory for role `{spec.role}`.")

    return await employee_service.create_employee(
        EmployeeCreate(
            name=spec.name,
            role=spec.role,
            description=spec.description,
        )
    )


async def ensure_demo_employees(employee_service: EmployeeServiceLike) -> list[Any]:
    return [await ensure_builtin_agent(employee_service)]


def _match_agent_from_list(selector: str, employees: Sequence[Any]) -> Any | None:
    key = _normalize(selector)
    spec = _find_builtin_agent_spec(selector)

    if spec is not None:
        for employee in employees:
            if (
                _normalize(employee.name) == _normalize(spec.name)
                and _normalize(employee.role) == _normalize(spec.role)
            ):
                return employee

    exact_matches = [
        employee for employee in employees
        if key in {
            _normalize(employee.id),
            _normalize(employee.name),
            _normalize(employee.role),
        }
    ]
    if exact_matches:
        return exact_matches[0]

    if spec is None:
        return None

    for employee in employees:
        if (
            _normalize(employee.name) == _normalize(spec.name)
            or _normalize(employee.role) == _normalize(spec.role)
        ):
            return employee
    return None


async def resolve_employee(
    employee_service: EmployeeServiceLike,
    selector: str,
    *,
    ensure_demo: bool,
) -> Any:
    return await resolve_agent(
        employee_service,
        selector,
        ensure_builtin=ensure_demo,
    )


async def resolve_agent(
    employee_service: EmployeeServiceLike,
    selector: str,
    *,
    ensure_builtin: bool,
) -> Any:
    if ensure_builtin:
        await ensure_builtin_agent(employee_service)
    employees = await employee_service.list_employees()
    employee = _match_agent_from_list(selector, employees)
    if employee is None:
        raise RuntimeError(
            f"Agent `{selector}` not found. Run `agent ensure` or `agent show` first."
        )
    return employee


async def resolve_session(
    session_service: SessionServiceLike,
    employee: Any,
    session_id: str,
) -> Any:
    sessions = await session_service.list_sessions(employee.id)
    session = _find_session_in_list(session_id, sessions)
    if session is None:
        raise RuntimeError(
            f"Session `{session_id}` not found for agent `{employee.name}`."
        )
    return session


def _decode_event(raw_event: dict[str, str]) -> tuple[str, dict[str, Any]]:
    event_type = raw_event.get("event", "")
    data = raw_event.get("data", "{}")
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        payload = {"raw": data}
    return event_type, payload


def _emit_event(event_type: str, payload: dict[str, Any], *, verbose: bool) -> None:
    if event_type == "message":
        text = payload.get("text", "")
        print(text, end="", flush=True)
        return
    if not verbose:
        return
    if event_type == "skill":
        status = payload.get("status", "start")
        print(f"\n[skill:{status}] {payload.get('name', '')}")
    elif event_type == "tool_call":
        print(f"\n[tool:start] {payload.get('name', '')}")
    elif event_type == "tool_result":
        result = "error" if payload.get("error") else "ok"
        print(f"\n[tool:{result}] {payload.get('summary', '')}")
    elif event_type == "thinking":
        text = payload.get("text", "").strip()
        if text:
            print(f"\n[thinking] {text}")


async def _send_streaming_message(
    session_service: Any,
    employee: Any,
    session_id: str,
    message: str,
    *,
    context: str | None,
    verbose: bool,
) -> None:
    printed_text = False
    async for raw_event in session_service.stream_message(
        employee.id,
        session_id,
        message,
        context=context,
    ):
        event_type, payload = _decode_event(raw_event)
        if event_type == "message" and payload.get("text"):
            printed_text = True
        _emit_event(event_type, payload, verbose=verbose)
    if printed_text:
        print()


async def _interactive_chat(
    session_service: Any,
    employee: Any,
    *,
    session_id: str | None,
    context: str | None,
    session_title: str,
    verbose: bool,
) -> int:
    if session_id:
        session = await resolve_session(session_service, employee, session_id)
        print(
            f"Chatting with {employee.name} ({employee.role}) in session "
            f"{session.id}. Type `/exit` to quit."
        )
    else:
        session = await session_service.create_session(employee.id, session_title)
        print(f"Chatting with {employee.name} ({employee.role}). Type `/exit` to quit.")
    while True:
        try:
            user_input = input("\nYou> ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("\nInterrupted.")
            return 130

        if not user_input:
            continue
        if user_input in {"/exit", "/quit"}:
            return 0

        print(f"{employee.name}> ", end="", flush=True)
        await _send_streaming_message(
            session_service,
            employee,
            session.id,
            user_input,
            context=context,
            verbose=verbose,
        )


async def cmd_agent_ensure(args: argparse.Namespace) -> int:
    employee_service = await _build_employee_service()
    existing = await employee_service.list_employees()
    existing_pairs = {
        (_normalize(employee.name), _normalize(employee.role))
        for employee in existing
    }
    employee = await ensure_builtin_agent(employee_service)
    pair = (_normalize(employee.name), _normalize(employee.role))
    status = "existing" if pair in existing_pairs else "created"
    print(f"{status}: {_format_employee_line(employee)}")
    return 0


async def cmd_agent_show(args: argparse.Namespace) -> int:
    employee_service = await _build_employee_service()
    if args.ensure:
        await ensure_builtin_agent(employee_service)
    employee = await resolve_agent(
        employee_service,
        BUILTIN_AGENT.key,
        ensure_builtin=False,
    )
    print(_format_employee_line(employee))
    description = getattr(employee, "description", "").strip()
    if description:
        print()
        print(description)
    return 0


async def cmd_employees_list(args: argparse.Namespace) -> int:
    employee_service = await _build_employee_service()
    if args.ensure_agent:
        await ensure_builtin_agent(employee_service)
    employees = await employee_service.list_employees()
    _print_employee_table(employees)
    return 0


async def cmd_sessions_list(args: argparse.Namespace) -> int:
    employee_service = await _build_employee_service()
    employee = await resolve_agent(
        employee_service,
        args.agent,
        ensure_builtin=args.ensure_agent,
    )
    session_service = await _build_session_service()
    sessions = await session_service.list_sessions(employee.id)
    _print_session_table(sessions)
    return 0


async def cmd_sessions_show(args: argparse.Namespace) -> int:
    employee_service = await _build_employee_service()
    employee = await resolve_agent(
        employee_service,
        args.agent,
        ensure_builtin=args.ensure_agent,
    )
    session_service = await _build_session_service()
    session = await resolve_session(session_service, employee, args.session_id)
    print(_format_session_line(session))
    print()
    messages = await session_service.list_messages(
        session.id,
        limit=max(args.limit, 0),
        offset=max(args.offset, 0),
    )
    _print_messages(messages)
    return 0


async def cmd_chat(args: argparse.Namespace) -> int:
    employee_service = await _build_employee_service()
    employee = await resolve_agent(
        employee_service,
        args.agent,
        ensure_builtin=not args.no_ensure_agent,
    )
    session_service = await _build_session_service()
    context = _context_from_args(args)

    if args.message:
        if args.session:
            session = await resolve_session(session_service, employee, args.session)
        else:
            title = args.session_title or _pick_initial_prompt(args.message)
            session = await session_service.create_session(employee.id, title)
        print(f"{employee.name}> ", end="", flush=True)
        await _send_streaming_message(
            session_service,
            employee,
            session.id,
            args.message,
            context=context,
            verbose=args.verbose,
        )
        return 0

    return await _interactive_chat(
        session_service,
        employee,
        session_id=args.session,
        context=context,
        session_title=args.session_title,
        verbose=args.verbose,
    )


async def async_main(argv: Sequence[str] | None = None) -> int:
    from common.database import close_db

    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        handler = getattr(args, "handler", None)
        if handler is None:
            parser.print_help()
            return 1
        return await handler(args)
    finally:
        await close_db()


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(async_main(argv))
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

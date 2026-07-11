from __future__ import annotations

import argparse

from .cli_chat import (
    _context_from_args,
    _interactive_chat,
    _pick_initial_prompt,
    _send_streaming_message,
)
from .cli_format import (
    _format_agent_line,
    _format_session_line,
    _print_messages,
    _print_session_table,
)
from .cli_smith import _build_agent_service, ensure_smith, resolve_session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smith",
        description="CLI for the resident Agent-Smith assistant.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    agent_parser = subparsers.add_parser("agent", help="Inspect the resident Smith agent.")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command", required=True)
    agent_ensure = agent_subparsers.add_parser("ensure", help="Initialize Smith if needed.")
    agent_ensure.set_defaults(handler=cmd_agent_ensure)
    agent_show = agent_subparsers.add_parser("show", help="Show the resident Smith profile.")
    agent_show.set_defaults(handler=cmd_agent_show)

    sessions_parser = subparsers.add_parser("sessions", help="Inspect Smith conversation sessions.")
    sessions_subparsers = sessions_parser.add_subparsers(dest="sessions_command", required=True)
    sessions_list = sessions_subparsers.add_parser("list", help="List Smith sessions.")
    sessions_list.set_defaults(handler=cmd_sessions_list)
    sessions_show = sessions_subparsers.add_parser("show", help="Show messages for one Smith session.")
    sessions_show.add_argument("session_id", help="Session id to inspect.")
    sessions_show.add_argument("--limit", type=int, default=0, help="Limit returned messages.")
    sessions_show.add_argument("--offset", type=int, default=0, help="Skip initial messages.")
    sessions_show.set_defaults(handler=cmd_sessions_show)

    chat_parser = subparsers.add_parser("chat", help="Chat with Smith.")
    chat_parser.add_argument("-m", "--message", help="Send one message and exit.")
    chat_parser.add_argument("--context", help="Context injected into the engine but not persisted.")
    chat_parser.add_argument("--workdir", help="Convenience alias for a working-directory context.")
    chat_parser.add_argument("--session-title", default="CLI Chat", help="Title for a new conversation.")
    chat_parser.add_argument("--session", help="Continue an existing session id.")
    chat_parser.add_argument(
        "--identity",
        help="YAML identity id for a new session; otherwise the first message selects one automatically.",
    )
    chat_parser.add_argument("--verbose", action="store_true", help="Show skill/tool/thinking trace.")
    chat_parser.set_defaults(handler=cmd_chat)
    return parser


async def cmd_agent_ensure(args: argparse.Namespace) -> int:
    agent = await ensure_smith(await _build_agent_service())
    print(f"ready: {_format_agent_line(agent)}")
    return 0


async def cmd_agent_show(args: argparse.Namespace) -> int:
    agent = await ensure_smith(await _build_agent_service())
    print(_format_agent_line(agent))
    description = getattr(agent, "description", "").strip()
    if description:
        print()
        print(description)
    return 0


async def cmd_sessions_list(args: argparse.Namespace) -> int:
    agent_service = await _build_agent_service()
    await ensure_smith(agent_service)
    _print_session_table(await agent_service.list_sessions())
    return 0


async def cmd_sessions_show(args: argparse.Namespace) -> int:
    agent_service = await _build_agent_service()
    await ensure_smith(agent_service)
    session = await resolve_session(agent_service, args.session_id)
    print(_format_session_line(session))
    print()
    _print_messages(
        await agent_service.list_messages(
            session.id,
            limit=max(args.limit, 0),
            offset=max(args.offset, 0),
        )
    )
    return 0


async def cmd_chat(args: argparse.Namespace) -> int:
    agent_service = await _build_agent_service()
    agent = await ensure_smith(agent_service)
    context = _context_from_args(args)

    if args.message:
        if args.session:
            session = await resolve_session(agent_service, args.session)
        else:
            title = args.session_title or _pick_initial_prompt(args.message)
            session = await agent_service.create_session(title, args.identity)
        print(f"{agent.name}> ", end="", flush=True)
        await _send_streaming_message(
            agent_service,
            session.id,
            args.message,
            context=context,
            verbose=args.verbose,
            identity_id=args.identity,
        )
        return 0

    return await _interactive_chat(
        agent_service,
        agent,
        session_id=args.session,
        context=context,
        session_title=args.session_title,
        verbose=args.verbose,
        identity_id=args.identity,
    )

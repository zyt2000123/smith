from __future__ import annotations

import argparse

from .cli_agents import (
    _build_agent_profile_service,
    _build_session_service,
    ensure_builtin_agent,
    resolve_agent,
    resolve_session,
)
from .cli_chat import (
    _context_from_args,
    _interactive_chat,
    _pick_initial_prompt,
    _send_streaming_message,
)
from .cli_format import (
    _format_agent_line,
    _format_session_line,
    _print_agent_table,
    _print_messages,
    _print_session_table,
)
from .cli_identity import BUILTIN_AGENT, _normalize


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smith",
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


async def cmd_agent_ensure(args: argparse.Namespace) -> int:
    agent_profile_service = await _build_agent_profile_service()
    existing = await agent_profile_service.list_profiles()
    existing_pairs = {
        (_normalize(agent.name), _normalize(agent.role))
        for agent in existing
    }
    agent = await ensure_builtin_agent(agent_profile_service)
    pair = (_normalize(agent.name), _normalize(agent.role))
    status = "existing" if pair in existing_pairs else "created"
    print(f"{status}: {_format_agent_line(agent)}")
    return 0


async def cmd_agent_show(args: argparse.Namespace) -> int:
    agent_profile_service = await _build_agent_profile_service()
    if args.ensure:
        await ensure_builtin_agent(agent_profile_service)
    agent = await resolve_agent(
        agent_profile_service,
        BUILTIN_AGENT.key,
        ensure_builtin=False,
    )
    print(_format_agent_line(agent))
    description = getattr(agent, "description", "").strip()
    if description:
        print()
        print(description)
    return 0


async def cmd_agents_list(args: argparse.Namespace) -> int:
    agent_profile_service = await _build_agent_profile_service()
    if args.ensure_agent:
        await ensure_builtin_agent(agent_profile_service)
    agents = await agent_profile_service.list_profiles()
    _print_agent_table(agents)
    return 0


async def cmd_sessions_list(args: argparse.Namespace) -> int:
    agent_profile_service = await _build_agent_profile_service()
    agent = await resolve_agent(
        agent_profile_service,
        args.agent,
        ensure_builtin=args.ensure_agent,
    )
    session_service = await _build_session_service()
    sessions = await session_service.list_sessions(agent.id)
    _print_session_table(sessions)
    return 0


async def cmd_sessions_show(args: argparse.Namespace) -> int:
    agent_profile_service = await _build_agent_profile_service()
    agent = await resolve_agent(
        agent_profile_service,
        args.agent,
        ensure_builtin=args.ensure_agent,
    )
    session_service = await _build_session_service()
    session = await resolve_session(session_service, agent, args.session_id)
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
    agent_profile_service = await _build_agent_profile_service()
    agent = await resolve_agent(
        agent_profile_service,
        args.agent,
        ensure_builtin=not args.no_ensure_agent,
    )
    session_service = await _build_session_service()
    context = _context_from_args(args)

    if args.message:
        if args.session:
            session = await resolve_session(session_service, agent, args.session)
        else:
            title = args.session_title or _pick_initial_prompt(args.message)
            session = await session_service.create_session(agent.id, title)
        print(f"{agent.name}> ", end="", flush=True)
        await _send_streaming_message(
            session_service,
            agent,
            session.id,
            args.message,
            context=context,
            verbose=args.verbose,
        )
        return 0

    return await _interactive_chat(
        session_service,
        agent,
        session_id=args.session,
        context=context,
        session_title=args.session_title,
        verbose=args.verbose,
    )

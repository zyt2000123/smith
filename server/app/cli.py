from __future__ import annotations

import asyncio
import sys
from typing import Sequence

from .cli_agents import (  # noqa: E402
    _build_agent_profile_service,
    _build_session_service,
    _find_session_in_list,
    ensure_builtin_agent,
    ensure_demo_agents,
    resolve_agent,
    resolve_session,
)
from .cli_chat import (  # noqa: E402
    _context_from_args,
    _decode_event,
    _emit_event,
    _interactive_chat,
    _pick_initial_prompt,
    _send_streaming_message,
)
from .cli_commands import (  # noqa: E402
    build_parser,
    cmd_agent_ensure,
    cmd_agent_show,
    cmd_chat,
    cmd_agents_list,
    cmd_sessions_list,
    cmd_sessions_show,
)
from .cli_format import (  # noqa: E402
    _format_agent_line,
    _format_session_line,
    _print_agent_table,
    _print_messages,
    _print_session_table,
)
from .cli_identity import (  # noqa: E402
    BUILTIN_AGENT,
    SHELL_ALIASES,
    BuiltInAgentSpec,
    AgentProfileServiceLike,
    SessionServiceLike,
    _find_builtin_agent_spec,
    _normalize,
)
from .cli_shell import (  # noqa: E402
    _extract_shell_argv,
    _launch_shell,
    _normalize_argv,
    _repo_root,
    _shell_entry_path,
    _should_launch_shell,
)


__all__ = [
    "BUILTIN_AGENT",
    "SHELL_ALIASES",
    "BuiltInAgentSpec",
    "AgentProfileServiceLike",
    "SessionServiceLike",
    "_build_agent_profile_service",
    "_build_session_service",
    "_context_from_args",
    "_decode_event",
    "_emit_event",
    "_extract_shell_argv",
    "_find_builtin_agent_spec",
    "_find_session_in_list",
    "_format_agent_line",
    "_format_session_line",
    "_interactive_chat",
    "_launch_shell",
    "_normalize",
    "_normalize_argv",
    "_pick_initial_prompt",
    "_print_agent_table",
    "_print_messages",
    "_print_session_table",
    "_repo_root",
    "_send_streaming_message",
    "_shell_entry_path",
    "_should_launch_shell",
    "async_main",
    "build_parser",
    "cmd_agent_ensure",
    "cmd_agent_show",
    "cmd_chat",
    "cmd_agents_list",
    "cmd_sessions_list",
    "cmd_sessions_show",
    "ensure_builtin_agent",
    "ensure_demo_agents",
    "main",
    "resolve_agent",
    "resolve_session",
]


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
    normalized_argv = _normalize_argv(argv)
    try:
        if _should_launch_shell(normalized_argv):
            return _launch_shell(normalized_argv)
        return asyncio.run(async_main(normalized_argv))
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

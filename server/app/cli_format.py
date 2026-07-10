from __future__ import annotations

from typing import Any, Sequence


def _format_agent_line(agent: Any) -> str:
    role = getattr(agent, "role", "")
    status = "online" if getattr(agent, "online", False) else "offline"
    return f"{agent.id}  {agent.name}  role={role}  status={status}"


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


def _print_agent_table(agents: Sequence[Any]) -> None:
    if not agents:
        print(
            "No agent records found. Run `agent ensure` to create the built-in "
            "personal assistant."
        )
        return
    for agent in agents:
        print(_format_agent_line(agent))


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

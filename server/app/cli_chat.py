from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .cli_smith import resolve_session

_ANSI_ESCAPE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|\x1b\[[\d;]*[A-Za-z]|\x1b][^\x07]*\x07|\x1b[^[\]()]")


def _sanitize_output(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _context_from_args(args: Any) -> str | None:
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
    lines = message.strip().splitlines()
    first_line = lines[0].strip() if lines else ""
    if not first_line:
        return "CLI Chat"
    return first_line[:40]


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
        text = _sanitize_output(payload.get("text", ""))
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
    agent_service: Any,
    session_id: str,
    message: str,
    *,
    context: str | None,
    verbose: bool,
    identity_id: str | None = None,
) -> None:
    printed_text = False
    async for raw_event in agent_service.stream_message(
        session_id,
        message,
        context=context,
        identity_id=identity_id,
    ):
        event_type, payload = _decode_event(raw_event)
        if event_type == "message" and payload.get("text"):
            printed_text = True
        _emit_event(event_type, payload, verbose=verbose)
    if printed_text:
        print()


async def _interactive_chat(
    agent_service: Any,
    agent: Any,
    *,
    session_id: str | None,
    context: str | None,
    session_title: str,
    verbose: bool,
    identity_id: str | None = None,
) -> int:
    if session_id:
        session = await resolve_session(agent_service, session_id)
        print(
            f"Chatting with {agent.name} ({agent.role}) in session "
            f"{session.id}. Type `/exit` to quit."
        )
    else:
        session = await agent_service.create_session(session_title, identity_id)
        print(f"Chatting with {agent.name} ({agent.role}). Type `/exit` to quit.")
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

        print(f"{agent.name}> ", end="", flush=True)
        await _send_streaming_message(
            agent_service,
            session.id,
            user_input,
            context=context,
            verbose=verbose,
            identity_id=identity_id,
        )

from __future__ import annotations

"""Shell command tool provider — executes commands with timeout and output limits."""

import asyncio
import os

TOOL_META = {
    "name": "shell",
    "description": "Execute a shell command and return its output. Has timeout and output size limits.",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 30, max 120)",
                "default": 30
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for command execution"
            }
        },
        "required": ["command"]
    }
}

MAX_OUTPUT = 10 * 1024  # 10KB
MAX_TIMEOUT = 120


async def execute(
    *, command: str, timeout: int = 30, cwd: str | None = None
) -> str:
    timeout = min(max(1, timeout), MAX_TIMEOUT)

    if cwd and not os.path.isdir(cwd):
        return f"Error: working directory does not exist: {cwd}"

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return f"Error: command timed out after {timeout}s"
    except Exception as e:
        return f"Error executing command: {e}"

    output_parts = []

    stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
    stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

    if stdout_text:
        if len(stdout_text) > MAX_OUTPUT:
            stdout_text = stdout_text[:MAX_OUTPUT] + f"\n... (truncated, {len(stdout)} bytes total)"
        output_parts.append(stdout_text)

    if stderr_text:
        if len(stderr_text) > MAX_OUTPUT:
            stderr_text = stderr_text[:MAX_OUTPUT] + f"\n... (truncated, {len(stderr)} bytes total)"
        output_parts.append(f"[stderr]\n{stderr_text}")

    exit_code = proc.returncode
    result = "\n".join(output_parts) if output_parts else "(no output)"
    return f"[exit_code={exit_code}]\n{result}"

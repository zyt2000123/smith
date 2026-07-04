"""Read file tool provider — reads local file content with safety limits."""

import os

TOOL_META = {
    "name": "read_file",
    "description": "Read the content of a local file. Returns text content with line numbers.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file to read"
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (0-based)",
                "default": 0
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read",
                "default": 500
            }
        },
        "required": ["path"]
    }
}

MAX_FILE_SIZE = 50 * 1024  # 50KB


async def execute(*, path: str, offset: int = 0, limit: int = 500) -> str:
    resolved = os.path.realpath(path)

    if not os.path.exists(resolved):
        return f"Error: file not found: {resolved}"

    if not os.path.isfile(resolved):
        return f"Error: not a regular file: {resolved}"

    file_size = os.path.getsize(resolved)
    if file_size > MAX_FILE_SIZE:
        return (
            f"Error: file too large ({file_size} bytes, max {MAX_FILE_SIZE} bytes). "
            f"Use offset/limit to read a portion."
        )

    try:
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except PermissionError:
        return f"Error: permission denied: {resolved}"
    except Exception as e:
        return f"Error reading file: {e}"

    total_lines = len(lines)
    start = max(0, offset)
    end = min(total_lines, start + limit)
    selected = lines[start:end]

    numbered = []
    for i, line in enumerate(selected, start=start + 1):
        numbered.append(f"{i}\t{line.rstrip()}")

    header = f"# {resolved} ({total_lines} lines total, showing {start + 1}-{end})"
    return header + "\n" + "\n".join(numbered)

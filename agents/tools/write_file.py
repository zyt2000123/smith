"""Write file tool provider — writes content to a file within the work directory."""

import os

TOOL_META = {
    "name": "write_file",
    "description": "Write content to a local file. Creates parent directories if needed.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write (must be within work directory)"
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file"
            },
            "append": {
                "type": "boolean",
                "description": "If true, append to existing file instead of overwriting",
                "default": False
            }
        },
        "required": ["path", "content"]
    },
    "path_args": ["path"],
    "is_write_tool": True,
}


def _is_within_workdir(path: str, work_dir: str) -> bool:
    resolved = os.path.realpath(path)
    work_resolved = os.path.realpath(work_dir)
    return resolved.startswith(work_resolved + os.sep) or resolved == work_resolved


async def execute(
    *, path: str, content: str, append: bool = False, _work_dir: str = ""
) -> str:
    if _work_dir and not _is_within_workdir(path, _work_dir):
        return (
            f"Error: path '{path}' is outside the allowed work directory '{_work_dir}'"
        )

    resolved = os.path.realpath(path) if os.path.isabs(path) else os.path.abspath(path)

    parent = os.path.dirname(resolved)
    if not os.path.exists(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as e:
            return f"Error: cannot create directory {parent}: {e}"

    # ponytail: snapshot before overwrite; skip on append (no data loss)
    if not append:
        try:
            from engine.snapshot import get_snapshot
            get_snapshot().track(resolved)
        except Exception:
            pass

    mode = "a" if append else "w"
    try:
        with open(resolved, mode, encoding="utf-8") as f:
            f.write(content)
    except PermissionError:
        return f"Error: permission denied: {resolved}"
    except Exception as e:
        return f"Error writing file: {e}"

    action = "appended to" if append else "wrote"
    size = len(content.encode("utf-8"))
    return f"OK: {action} {resolved} ({size} bytes)"

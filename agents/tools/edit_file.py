"""Edit file tool — precise string replacement without full rewrite."""

import os

TOOL_META = {
    "name": "edit_file",
    "description": (
        "Replace a specific string in a file. The old_string must appear exactly once "
        "in the file (unless replace_all is true). Use read_file first to see the exact content. "
        "For new files or full rewrites, use write_file instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to edit"},
            "old_string": {"type": "string", "description": "Exact text to find and replace"},
            "new_string": {"type": "string", "description": "Replacement text"},
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences instead of requiring uniqueness",
                "default": False,
            },
        },
        "required": ["path", "old_string", "new_string"],
    },
}


async def execute(
    *, path: str, old_string: str, new_string: str, replace_all: bool = False,
) -> str:
    if old_string == new_string:
        return "Error: new_string must differ from old_string"

    resolved = os.path.realpath(path) if os.path.isabs(path) else os.path.abspath(path)

    if not os.path.isfile(resolved):
        return f"Error: file not found: {resolved}"

    try:
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except PermissionError:
        return f"Error: permission denied: {resolved}"

    count = content.count(old_string)
    if count == 0:
        return (
            f"Error: old_string not found in {resolved}. "
            "Make sure you copied the exact text including whitespace and indentation."
        )

    if count > 1 and not replace_all:
        return (
            f"Error: old_string appears {count} times in {resolved}. "
            "Provide more surrounding context to make it unique, or set replace_all=true."
        )

    try:
        from engine.snapshot import get_snapshot
        get_snapshot().track(resolved)
    except Exception:
        pass

    updated = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)

    try:
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(updated)
    except PermissionError:
        return f"Error: permission denied writing: {resolved}"

    replacements = count if replace_all else 1
    return f"OK: edited {resolved} ({replacements} replacement{'s' if replacements > 1 else ''})"

"""Glob tool — find files by pattern."""

import glob as _glob
import os

TOOL_META = {
    "name": "glob_files",
    "description": (
        "Find files matching a glob pattern. Returns relative paths. "
        "Examples: '**/*.py', 'src/**/*.ts', '**/test_*.py'"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern, e.g. '**/*.py'"},
            "path": {"type": "string", "description": "Base directory to search from", "default": "."},
        },
        "required": ["pattern"],
    },
}

MAX_RESULTS = 200
EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", ".build"}


async def execute(*, pattern: str, path: str = ".") -> str:
    base = os.path.abspath(path)
    if not os.path.isdir(base):
        return f"Error: directory not found: {base}"

    matches = sorted(_glob.glob(os.path.join(base, pattern), recursive=True))
    filtered = [
        os.path.relpath(m, base) for m in matches
        if os.path.isfile(m) and not any(p in EXCLUDED_DIRS for p in m.replace(base, "").split(os.sep))
    ]

    total = len(filtered)
    filtered = filtered[:MAX_RESULTS]
    if not filtered:
        return f"No files found matching: {pattern}"

    header = f"# {min(total, MAX_RESULTS)} file{'s' if len(filtered) != 1 else ''}"
    if total > MAX_RESULTS:
        header += f" (showing {MAX_RESULTS} of {total})"
    return header + "\n" + "\n".join(filtered)

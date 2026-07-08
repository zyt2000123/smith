"""Todo tool — track tasks during a session."""

TOOL_META = {
    "name": "todo",
    "description": (
        "Manage a task list for the current session. Use to track multi-step work, "
        "show progress to the user, and organize complex tasks. "
        "Actions: list, add, update, remove, clear."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "add", "update", "remove", "clear"],
                "description": "Action to perform",
            },
            "text": {"type": "string", "description": "Task description (for add)"},
            "index": {"type": "integer", "description": "Task index (for update/remove, 1-based)"},
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "done"],
                "description": "New status (for update)",
            },
        },
        "required": ["action"],
    },
}

_todos: list[dict] = []
_ICONS = {"pending": "○", "in_progress": "◐", "done": "●"}


def _fmt() -> str:
    if not _todos:
        return "No tasks."
    lines = [f"{i}. {_ICONS.get(t['status'],'?')} [{t['status']}] {t['text']}" for i, t in enumerate(_todos, 1)]
    done = sum(1 for t in _todos if t["status"] == "done")
    lines.append(f"\nProgress: {done}/{len(_todos)} done")
    return "\n".join(lines)


async def execute(*, action: str, text: str = "", index: int = 0, status: str = "pending") -> str:
    if action == "list":
        return _fmt()
    if action == "add":
        if not text.strip():
            return "Error: text is required for add"
        _todos.append({"text": text.strip(), "status": "pending"})
        return f"Added task {len(_todos)}: {text.strip()}\n\n{_fmt()}"
    if action == "update":
        if index < 1 or index > len(_todos):
            return f"Error: invalid index {index}. Tasks: 1-{len(_todos)}"
        _todos[index - 1]["status"] = status
        if text.strip():
            _todos[index - 1]["text"] = text.strip()
        return f"Updated task {index}.\n\n{_fmt()}"
    if action == "remove":
        if index < 1 or index > len(_todos):
            return f"Error: invalid index {index}. Tasks: 1-{len(_todos)}"
        removed = _todos.pop(index - 1)
        return f"Removed: {removed['text']}\n\n{_fmt()}"
    if action == "clear":
        n = len(_todos)
        _todos.clear()
        return f"Cleared {n} task(s)."
    return f"Error: unknown action '{action}'"

from __future__ import annotations

"""Memory operations tool provider — CRUD for employee memory directory.

Unified with engine/memory/store.py: both read/write .md files with YAML
frontmatter in ~/.agent-smith/employees/<id>/memory/.  This ensures the
prompt assembler sees memories written by the agent tool and vice-versa.
"""

import json
import re
from pathlib import Path

TOOL_META = {
    "name": "memory_ops",
    "description": "Memory CRUD operations: search, add, update, and remove memory entries for an employee.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "add", "update", "remove"],
                "description": "The memory operation to perform",
            },
            "employee_id": {
                "type": "string",
                "description": "Employee identifier (used to locate memory directory)",
            },
            "query": {
                "type": "string",
                "description": "Search query string (required for search)",
            },
            "content": {
                "type": "string",
                "description": "Memory content text (required for add/update)",
            },
            "evidence": {
                "type": "string",
                "description": "Evidence supporting this memory — every memory must have evidence (required for add/update)",
            },
            "scope": {
                "type": "string",
                "enum": ["agent", "project"],
                "description": "Memory scope (default: agent)",
            },
            "memory_id": {
                "type": "string",
                "description": "Memory entry id (required for update/remove)",
            },
        },
        "required": ["action", "employee_id"],
    },
}

# Patterns that indicate sensitive information — reject memories containing these
_SENSITIVE_PATTERNS = re.compile(
    r"(?i)"
    r"(?:sk-[a-zA-Z0-9]{20,})"        # OpenAI-style API keys
    r"|(?:token\s*[:=]\s*\S{10,})"     # token: ... or token=...
    r"|(?:api_key\s*[:=]\s*\S{10,})"   # api_key: ... or api_key=...
    r"|(?:password\s*[:=]\s*\S{4,})"   # password: ... or password=...
    r"|(?:secret\s*[:=]\s*\S{10,})"    # secret: ... or secret=...
    r"|(?:\+\d{10,15})"               # phone numbers (+1234567890...)
    r"|(?:chat_id\s*[:=]\s*\d{5,})"   # chat IDs
)


def _memory_dir(employee_id: str) -> Path:
    """Canonical memory directory: ~/.agent-smith/employees/<id>/memory/"""
    safe_id = Path(employee_id).name  # prevent path traversal
    return Path.home() / ".agent-smith" / "employees" / safe_id / "memory"


def _check_sensitive(text: str) -> str | None:
    """Return a rejection message if text contains sensitive information."""
    match = _SENSITIVE_PATTERNS.search(text)
    if match:
        return f"Memory rejected: contains sensitive information (matched near: {match.group()[:20]}...)"
    return None


def _memory_store(mem_dir: Path):
    try:
        from engine.memory.store import FileMemoryStore
    except ModuleNotFoundError:
        import sys
        project_root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(project_root))
        from engine.memory.store import FileMemoryStore
    return FileMemoryStore(mem_dir)


def _remove_legacy_duplicate(mem_dir: Path, memory_id: str) -> None:
    safe = Path(memory_id).name
    legacy = mem_dir / f"{safe}.md"
    if legacy.is_file():
        legacy.unlink()


async def execute(
    *,
    action: str,
    employee_id: str,
    query: str | None = None,
    content: str | None = None,
    evidence: str | None = None,
    scope: str | None = None,
    memory_id: str | None = None,
) -> str:
    mem_dir = _memory_dir(employee_id)
    scope = scope or "agent"
    if scope not in {"agent", "project"}:
        return "Error: 'scope' must be either 'agent' or 'project'"
    store = _memory_store(mem_dir)

    if action == "search":
        if not query:
            return "Error: 'query' is required for search action"

        keywords = query.lower().split()
        if not keywords:
            return "No keywords provided"

        matches: list[str] = []

        for entry in await store.search(query):
            matches.append(
                f"- [{entry.id}] ({entry.scope}) {entry.content[:120]}"
            )

        # Search recent.jsonl
        recent_file = mem_dir / "recent.jsonl"
        if recent_file.is_file():
            try:
                for line in recent_file.read_text(encoding="utf-8").strip().splitlines():
                    line_lower = line.lower()
                    if any(kw in line_lower for kw in keywords):
                        try:
                            entry = json.loads(line)
                            matches.append(
                                f"- [recent] {entry.get('task', '?')} -> {entry.get('summary', '?')[:80]}"
                            )
                        except json.JSONDecodeError:
                            continue
            except OSError:
                pass

        if not matches:
            return f"No matches for '{query}'"
        return f"Found {len(matches)} match(es):\n" + "\n".join(matches)

    elif action == "add":
        if not content:
            return "Error: 'content' is required for add action"
        if not evidence:
            return "Error: 'evidence' is required for add action (every memory must have evidence)"

        # Security check
        rejection = _check_sensitive(content) or _check_sensitive(evidence)
        if rejection:
            return rejection

        entry = await store.add(content, evidence, scope)
        return f"OK: added memory '{entry.id}' for employee '{employee_id}'"

    elif action == "update":
        if not memory_id:
            return "Error: 'memory_id' is required for update action"
        if not content:
            return "Error: 'content' is required for update action"
        if not evidence:
            return "Error: 'evidence' is required for update action (every memory must have evidence)"

        # Security check
        rejection = _check_sensitive(content) or _check_sensitive(evidence)
        if rejection:
            return rejection

        updated = await store.update(memory_id, content=content, evidence=evidence)
        if not updated:
            return f"Error: memory '{memory_id}' not found"
        _remove_legacy_duplicate(mem_dir, memory_id)
        return f"OK: updated memory '{memory_id}' for employee '{employee_id}'"

    elif action == "remove":
        if not memory_id:
            return "Error: 'memory_id' is required for remove action"

        removed = await store.remove(memory_id)
        if not removed:
            return f"Error: memory '{memory_id}' not found"
        _remove_legacy_duplicate(mem_dir, memory_id)
        return f"OK: removed memory '{memory_id}' for employee '{employee_id}'"

    else:
        return f"Error: unknown action '{action}'. Use: search, add, update, remove"

from __future__ import annotations

"""Memory operations tool provider — CRUD for employee memory directory.

Unified with engine/memory/store.py: both read/write .md files with YAML
frontmatter in ~/.agent-smith/employees/<id>/memory/.  This ensures the
prompt assembler sees memories written by the agent tool and vice-versa.
"""

import json
import re
import uuid
from datetime import datetime, timezone
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


def _scope_dirs(mem_dir: Path) -> list[Path]:
    """Entry locations in search-priority order: project/, agent/, root (legacy)."""
    return [mem_dir / "project", mem_dir / "agent", mem_dir]


def _all_entry_files(mem_dir: Path) -> list[Path]:
    """All entry .md files across scope dirs (project first) + legacy root files."""
    files: list[Path] = []
    for d in _scope_dirs(mem_dir):
        if d.is_dir():
            files.extend(sorted(f for f in d.glob("*.md") if f.is_file()))
    return files


def _find_entry(mem_dir: Path, memory_id: str) -> Path | None:
    """Locate an entry file by id across scope dirs and legacy root."""
    safe = Path(memory_id).name  # prevent path traversal
    for d in _scope_dirs(mem_dir):
        p = d / f"{safe}.md"
        if p.is_file():
            return p
    return None


def _check_sensitive(text: str) -> str | None:
    """Return a rejection message if text contains sensitive information."""
    match = _SENSITIVE_PATTERNS.search(text)
    if match:
        return f"Memory rejected: contains sensitive information (matched near: {match.group()[:20]}...)"
    return None


def _parse_md_file(path: Path) -> dict | None:
    """Parse a .md memory file with YAML frontmatter.

    Returns dict with keys: id, content, scope, evidence, created_at.
    Same format as engine/memory/store.py FileMemoryStore._parse_file.
    """
    raw = path.read_text(encoding="utf-8")
    entry_id = path.stem
    scope = "agent"
    created_at = ""
    last_accessed = ""
    body = raw

    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if line.startswith("scope:"):
                    scope = line.split(":", 1)[1].strip()
                elif line.startswith("created_at:"):
                    created_at = line.split(":", 1)[1].strip()
                elif line.startswith("last_accessed:"):
                    last_accessed = line.split(":", 1)[1].strip()
                elif line.startswith("id:"):
                    entry_id = line.split(":", 1)[1].strip()
            body = parts[2].strip()

    # Split body from evidence
    evidence = ""
    if "\nEvidence:" in body:
        body_part, evidence = body.rsplit("\nEvidence:", 1)
        body = body_part.strip()
        evidence = evidence.strip()

    return {
        "id": entry_id,
        "content": body,
        "scope": scope,
        "evidence": evidence,
        "created_at": created_at,
        "last_accessed": last_accessed or created_at,
    }


def _write_md_file(
    mem_dir: Path, entry_id: str, content: str, evidence: str,
    scope: str, created_at: str, last_accessed: str = "",
) -> Path:
    """Write a .md memory file with the same format and layout as FileMemoryStore."""
    target_dir = mem_dir / ("project" if scope == "project" else "agent")
    target_dir.mkdir(parents=True, exist_ok=True)
    text = (
        f"---\n"
        f"id: {entry_id}\n"
        f"scope: {scope}\n"
        f"created_at: {created_at}\n"
        f"last_accessed: {last_accessed or created_at}\n"
        f"---\n"
        f"{content}\n\n"
        f"Evidence: {evidence}\n"
    )
    target = target_dir / f"{entry_id}.md"
    target.write_text(text, encoding="utf-8")
    return target


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

    if action == "search":
        if not query:
            return "Error: 'query' is required for search action"

        keywords = query.lower().split()
        if not keywords:
            return "No keywords provided"

        matches: list[str] = []

        # Search .md entries across scope dirs (project first) + legacy root files
        for f in _all_entry_files(mem_dir):
            try:
                raw = f.read_text(encoding="utf-8").lower()
                if any(kw in raw for kw in keywords):
                    entry = _parse_md_file(f)
                    if entry:
                        matches.append(
                            f"- [{entry['id']}] ({entry['scope']}) {entry['content'][:120]}"
                        )
            except (OSError, UnicodeDecodeError):
                continue

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

        entry_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        _write_md_file(mem_dir, entry_id, content, evidence, scope, now)
        return f"OK: added memory '{entry_id}' for employee '{employee_id}'"

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

        found = _find_entry(mem_dir, memory_id)
        if found is None:
            return f"Error: memory '{memory_id}' not found"

        # Preserve original created_at + scope (like FileMemoryStore.update); refresh last_accessed
        now = datetime.now(timezone.utc).isoformat()
        old_entry = _parse_md_file(found)
        created_at = (old_entry or {}).get("created_at") or now
        entry_scope = (old_entry or {}).get("scope", "agent")

        new_path = _write_md_file(mem_dir, memory_id, content, evidence, entry_scope, created_at, last_accessed=now)
        if found != new_path:
            found.unlink()  # migrate legacy root-level entry into its scope dir
        return f"OK: updated memory '{memory_id}' for employee '{employee_id}'"

    elif action == "remove":
        if not memory_id:
            return "Error: 'memory_id' is required for remove action"

        found = _find_entry(mem_dir, memory_id)
        if found is None:
            return f"Error: memory '{memory_id}' not found"
        found.unlink()
        return f"OK: removed memory '{memory_id}' for employee '{employee_id}'"

    else:
        return f"Error: unknown action '{action}'. Use: search, add, update, remove"

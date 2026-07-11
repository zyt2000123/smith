from __future__ import annotations

"""Memory operations tool provider — CRUD for the agent's memory directory.

Unified with engine/memory/store.py: both read/write .md files with YAML
frontmatter under Smith's canonical memory directory. This ensures the prompt
assembler sees memories written by the agent tool and vice-versa.
"""

import json
import re
from pathlib import Path

TOOL_META = {
    "name": "memory_ops",
    "description": "Memory CRUD operations: search, add, update, and remove memory entries for an agent.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "add", "update", "remove", "episode"],
                "description": "The memory operation to perform",
            },
            "topic": {
                "type": "string",
                "description": "Episode topic name (required for episode action)",
            },
            "agent_id": {
                "type": "string",
                "description": "Agent identifier (used to locate memory directory)",
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
        "required": ["action", "agent_id"],
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


def _memory_dir(agent_id: str) -> Path:
    """Return Smith's single canonical memory directory."""
    try:
        from common.config import AGENT_DIR
    except ModuleNotFoundError:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from common.config import AGENT_DIR
    return AGENT_DIR / "memory"


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


async def execute(
    *,
    action: str,
    agent_id: str,
    query: str | None = None,
    content: str | None = None,
    evidence: str | None = None,
    scope: str | None = None,
    memory_id: str | None = None,
    topic: str | None = None,
) -> str:
    mem_dir = _memory_dir(agent_id)
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
        return f"OK: added memory '{entry.id}' for agent '{agent_id}'"

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
        return f"OK: updated memory '{memory_id}' for agent '{agent_id}'"

    elif action == "remove":
        if not memory_id:
            return "Error: 'memory_id' is required for remove action"

        removed = await store.remove(memory_id)
        if not removed:
            return f"Error: memory '{memory_id}' not found"
        return f"OK: removed memory '{memory_id}' for agent '{agent_id}'"

    elif action == "episode":
        if not topic:
            return "Error: 'topic' is required for episode action"

        # Load recent events and filter by topic keywords
        recent_file = mem_dir / "recent.jsonl"
        if not recent_file.is_file():
            return "Error: no recent events to summarize"

        topic_keywords = topic.lower().split()
        related: list[dict] = []
        for line in recent_file.read_text(encoding="utf-8").strip().splitlines():
            try:
                entry = json.loads(line)
                text = f"{entry.get('task', '')} {entry.get('summary', '')}".lower()
                if any(kw in text for kw in topic_keywords):
                    related.append(entry)
            except json.JSONDecodeError:
                continue

        if not related:
            return f"No events found matching topic '{topic}'"

        try:
            from engine.memory.compile import compact_episode
            from engine.llm.model_config import resolve_llm_config, build_llm_client

            llm_cfg = resolve_llm_config()
            if not llm_cfg.get("api_key"):
                return "Error: no LLM API key configured — cannot generate episode"

            llm = build_llm_client(llm_cfg)
            try:
                path = await compact_episode(mem_dir, llm, topic, related)
            finally:
                await llm.close()

            if path:
                return f"OK: episode saved to {path.name} ({len(related)} related events)"
            return "Error: episode generation returned no output"
        except Exception as e:
            return f"Error generating episode: {type(e).__name__}: {e}"

    else:
        return f"Error: unknown action '{action}'. Use: search, add, update, remove, episode"

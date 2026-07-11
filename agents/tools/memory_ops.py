"""Memory operations tool provider — CRUD for the agent's memory.

Aligned with engine/memory pipeline:
  - add: appends to recent.jsonl (gets compiled into recent.md/durable.md)
  - search: searches across compiled layers + episodes + recent events
  - episode: creates an episode archive (wiki mode)
  - update/remove: operate on episodes only
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

TOOL_META = {
    "name": "memory_ops",
    "description": "Memory operations: search memories, add events, manage episodes.",
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
            "query": {
                "type": "string",
                "description": "Search query string (required for search)",
            },
            "content": {
                "type": "string",
                "description": "Memory content (required for add/update)",
            },
            "evidence": {
                "type": "string",
                "description": "Evidence supporting this memory (required for add)",
            },
            "episode_id": {
                "type": "string",
                "description": "Episode file stem (required for update/remove)",
            },
        },
        "required": ["action"],
    },
}

def _memory_dir() -> Path:
    try:
        from common.config import AGENT_DIR
    except ModuleNotFoundError:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from common.config import AGENT_DIR
    return AGENT_DIR / "memory"


def _check_sensitive(text: str) -> str | None:
    try:
        from engine.memory._files import contains_secret
    except ModuleNotFoundError:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from engine.memory._files import contains_secret
    if contains_secret(text):
        return "Memory rejected: contains sensitive information"
    return None


async def execute(
    *,
    action: str,
    query: str | None = None,
    content: str | None = None,
    evidence: str | None = None,
    topic: str | None = None,
    episode_id: str | None = None,
    **_: object,
) -> str:
    mem_dir = _memory_dir()
    mem_dir.mkdir(parents=True, exist_ok=True)

    if action == "search":
        if not query:
            return "Error: 'query' is required for search action"
        return await _search(mem_dir, query)

    elif action == "add":
        if not content:
            return "Error: 'content' is required for add action"
        if not evidence:
            return "Error: 'evidence' is required for add action"
        rejection = _check_sensitive(content) or _check_sensitive(evidence)
        if rejection:
            return rejection
        return _append_event(mem_dir, content, evidence)

    elif action == "episode":
        if not topic:
            return "Error: 'topic' is required for episode action"
        return await _create_episode(mem_dir, topic)

    elif action == "update":
        if not episode_id:
            return "Error: 'episode_id' is required for update action"
        if not content:
            return "Error: 'content' is required for update action"
        rejection = _check_sensitive(content)
        if rejection:
            return rejection
        return _update_episode(mem_dir, episode_id, content)

    elif action == "remove":
        if not episode_id:
            return "Error: 'episode_id' is required for remove action"
        return await _remove_episode(mem_dir, episode_id)

    return f"Error: unknown action '{action}'. Use: search, add, episode, update, remove"


def _append_event(mem_dir: Path, content: str, evidence: str) -> str:
    """Append to recent.jsonl so it enters the compilation pipeline."""
    recent_file = mem_dir / "recent.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "task": f"[memory] {content}",
        "summary": f"Evidence: {evidence}",
        "timestamp": now,
    }
    with open(recent_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return "OK: memory event recorded (will be compiled into durable memory)"


async def _search(mem_dir: Path, query: str) -> str:
    keywords = query.lower().split()
    if not keywords:
        return "No keywords provided"

    matches: list[str] = []

    for name in ("durable.md", "recent.md"):
        path = mem_dir / name
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            if any(kw in content.lower() for kw in keywords):
                matches.append(f"- [{name}] {content[:200]}")

    episodes_dir = mem_dir / "episodes"
    if episodes_dir.is_dir():
        for ep in sorted(episodes_dir.glob("*.md")):
            content = ep.read_text(encoding="utf-8")
            if any(kw in content.lower() for kw in keywords):
                matches.append(f"- [episode:{ep.stem}] {content[:120]}")

    recent_file = mem_dir / "recent.jsonl"
    if recent_file.is_file():
        try:
            for line in recent_file.read_text(encoding="utf-8").strip().splitlines()[-20:]:
                if any(kw in line.lower() for kw in keywords):
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


async def _create_episode(mem_dir: Path, topic: str) -> str:
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
        from engine.llm.model_config import LLMUsage, resolve_llm_config, build_llm_client

        gen_cfg = resolve_llm_config(usage=LLMUsage.BACKGROUND)
        if not gen_cfg.get("api_key"):
            return "Error: no LLM API key configured — cannot generate episode"

        generator = build_llm_client(gen_cfg)
        reviewer = None
        try:
            rev_cfg = resolve_llm_config(usage=LLMUsage.GATE)
            if rev_cfg.get("api_key"):
                reviewer = build_llm_client(rev_cfg)
            path = await compact_episode(mem_dir, generator, topic, related, reviewer=reviewer)
        finally:
            await generator.close()
            if reviewer:
                await reviewer.close()

        if path:
            return f"OK: episode saved to {path.name} ({len(related)} related events)"
        return "Error: episode generation returned no output"
    except Exception as e:
        return f"Error generating episode: {type(e).__name__}: {e}"


def _update_episode(mem_dir: Path, episode_id: str, content: str) -> str:
    if Path(episode_id).name != episode_id:
        return "Error: invalid episode_id"
    ep_path = mem_dir / "episodes" / f"{episode_id}.md"
    if not ep_path.is_file():
        return f"Error: episode '{episode_id}' not found"
    ep_root = (mem_dir / "episodes").resolve()
    if not ep_path.resolve().is_relative_to(ep_root):
        return "Error: invalid episode path"

    from engine.memory._files import atomic_write_text
    atomic_write_text(ep_path, content)
    return f"OK: updated episode '{episode_id}'"


async def _remove_episode(mem_dir: Path, episode_id: str) -> str:
    if Path(episode_id).name != episode_id:
        return "Error: invalid episode_id"
    ep_path = mem_dir / "episodes" / f"{episode_id}.md"
    if not ep_path.is_file():
        return f"Error: episode '{episode_id}' not found"
    ep_root = (mem_dir / "episodes").resolve()
    if not ep_path.resolve().is_relative_to(ep_root):
        return "Error: invalid episode path"

    ep_path.unlink()
    try:
        from engine.memory.search import SearchIndex
        idx = SearchIndex(mem_dir / "episodes")
        await idx.open()
        try:
            await idx.remove_entry(episode_id)
        finally:
            await idx.close()
    except Exception:
        return f"OK: removed episode '{episode_id}' (search index update failed — will self-heal)"
    return f"OK: removed episode '{episode_id}'"

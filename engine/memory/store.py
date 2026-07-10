"""Memory store — recent.jsonl as sole event source + episode FTS5 search.

FileMemoryStore is retained for backward compat with dream.py (pending redesign).
New conversation memories are NOT written as .md entries — recent.jsonl is the
sole event source. See compile.py for the compilation pipeline.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .interface import MemoryEntry


# ---------------------------------------------------------------------------
# Legacy FileMemoryStore — retained for Dream migration
# ---------------------------------------------------------------------------


class FileMemoryStore:
    """Legacy file-based memory store with scope-based subdirectories.

    New conversation memories are no longer written here.
    Kept temporarily for Dream migration and backward compatibility.
    """

    def __init__(self, memory_dir: Path) -> None:
        self._dir = memory_dir
        self._agent_dir = memory_dir / "agent"
        self._project_dir = memory_dir / "project"

    def _all_md_files(self) -> list[tuple[Path, str]]:
        files: list[tuple[Path, str]] = []
        for scope_dir, scope in [(self._project_dir, "project"), (self._agent_dir, "agent")]:
            if scope_dir.is_dir():
                for f in sorted(scope_dir.glob("*.md")):
                    files.append((f, scope))
        return files

    async def search(self, query: str) -> list[MemoryEntry]:
        """Keyword scan over legacy .md entries."""
        keywords = query.lower().split()
        if not keywords:
            return []
        results: list[MemoryEntry] = []
        for path, scope in self._all_md_files():
            content = path.read_text(encoding="utf-8")
            if any(kw in content.lower() for kw in keywords):
                entry = self._parse_file(path, content, scope)
                if entry:
                    results.append(entry)
        return results

    async def list_all(self) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        for path, scope in self._all_md_files():
            raw = path.read_text(encoding="utf-8")
            entry = self._parse_file(path, raw, scope)
            if entry:
                entries.append(entry)
        return entries

    async def add(self, content: str, evidence: str, scope: str) -> MemoryEntry:
        entry_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        entry = MemoryEntry(id=entry_id, content=content, scope=scope, evidence=evidence, created_at=now, last_accessed=now)
        target_dir = self._project_dir if scope == "project" else self._agent_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        text = f"---\nid: {entry.id}\nscope: {entry.scope}\ncreated_at: {entry.created_at}\nlast_accessed: {entry.last_accessed}\n---\n{entry.content}\n\nEvidence: {entry.evidence}\n"
        (target_dir / f"{entry.id}.md").write_text(text, encoding="utf-8")
        return entry

    async def update(self, entry_id: str, content: str | None = None, evidence: str | None = None) -> bool:
        """Update a legacy .md entry."""
        for scope_dir, scope in [(self._project_dir, "project"), (self._agent_dir, "agent")]:
            if not scope_dir.is_dir():
                continue
            path = scope_dir / f"{entry_id}.md"
            if path.is_file():
                raw = path.read_text(encoding="utf-8")
                entry = self._parse_file(path, raw, scope)
                if entry is None:
                    return False
                if content is not None:
                    entry.content = content
                if evidence is not None:
                    entry.evidence = evidence
                entry.last_accessed = datetime.now(timezone.utc).isoformat()
                target_dir = self._project_dir if entry.scope == "project" else self._agent_dir
                text = f"---\nid: {entry.id}\nscope: {entry.scope}\ncreated_at: {entry.created_at}\nlast_accessed: {entry.last_accessed}\n---\n{entry.content}\n\nEvidence: {entry.evidence}\n"
                (target_dir / f"{entry.id}.md").write_text(text, encoding="utf-8")
                return True
        return False

    async def remove(self, entry_id: str) -> bool:
        for scope_dir in (self._project_dir, self._agent_dir):
            if not scope_dir.is_dir():
                continue
            path = scope_dir / f"{entry_id}.md"
            if path.is_file():
                path.unlink()
                return True
        return False

    @staticmethod
    def _parse_file(path: Path, raw: str, default_scope: str = "agent") -> MemoryEntry | None:
        entry_id = path.stem
        scope = default_scope
        created_at = last_accessed = ""
        body = raw

        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().splitlines():
                    key, _, val = line.partition(":")
                    val = val.strip()
                    if key == "scope": scope = val
                    elif key == "created_at": created_at = val
                    elif key == "last_accessed": last_accessed = val
                    elif key == "id": entry_id = val
                body = parts[2].strip()

        evidence = ""
        if "\nEvidence:" in body:
            body, evidence = body.rsplit("\nEvidence:", 1)
            body = body.strip()
            evidence = evidence.strip()

        return MemoryEntry(id=entry_id, content=body, scope=scope, evidence=evidence, created_at=created_at, last_accessed=last_accessed or created_at)


# ---------------------------------------------------------------------------
# Query-time retrieval: search episodes via FTS5
# ---------------------------------------------------------------------------

_MAX_EPISODE_CONTEXT_CHARS = 6000


async def search_relevant_memories(agent_dir: Path, query: str, top_k: int = 3) -> str:
    """Search episode summaries relevant to *query* for prompt injection.

    durable.md and recent.md are already injected by assembler (fixed);
    this function only searches episodes (on-demand). Returns "" on any
    failure so prompt assembly never blocks.
    """
    episodes_dir = agent_dir / "memory" / "episodes"
    if not episodes_dir.is_dir() or not query.strip():
        return ""

    try:
        from .search import SearchIndex

        idx = SearchIndex(episodes_dir)
        await idx.open()
        try:
            episodes = list(episodes_dir.glob("*.md"))
            if not episodes:
                return ""

            for ep in episodes:
                content = ep.read_text(encoding="utf-8")
                await idx.index_entry(ep.stem, content, "episode")

            hits = await idx.search(query, top_k)
            if not hits:
                return ""

            lines = ["## Relevant Episodes"]
            total_chars = 0
            for hit in hits:
                ep_path = episodes_dir / f"{hit['id']}.md"
                if not ep_path.is_file():
                    continue
                content = ep_path.read_text(encoding="utf-8").strip()
                if total_chars + len(content) > _MAX_EPISODE_CONTEXT_CHARS:
                    break
                lines.append(content)
                total_chars += len(content)

            return "\n\n".join(lines) if len(lines) > 1 else ""
        finally:
            await idx.close()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Conversation-level memory persistence
# ---------------------------------------------------------------------------

_COMPILE_INTERVAL = 5


async def save_conversation_memory(
    agent_dir: Path, user_msg: str, reply: str, had_tools: bool
) -> None:
    """Append to recent.jsonl and periodically trigger compilation.

    Dream consolidation is temporarily disabled. The current DreamConsolidator
    operates on legacy FileMemoryStore entries and will be redesigned to
    maintain durable.md in a later migration.
    """
    if not had_tools:
        return

    memory_dir = agent_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    recent_file = memory_dir / "recent.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    entry = {"task": user_msg[:100], "summary": reply[:200], "timestamp": now}

    with open(recent_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Periodic compilation (recent + durable)
    counter_file = memory_dir / ".compile_counter"
    count = 0
    if counter_file.is_file():
        try:
            count = int(counter_file.read_text().strip())
        except (ValueError, OSError):
            count = 0
    count += 1
    counter_file.write_text(str(count), encoding="utf-8")

    if count >= _COMPILE_INTERVAL:
        counter_file.write_text("0", encoding="utf-8")
        try:
            from .compile import run_compilation
            from engine.llm.model_config import resolve_llm_config, build_llm_client

            llm_cfg = resolve_llm_config(agent_dir.name)
            if llm_cfg.get("api_key"):
                llm = build_llm_client(llm_cfg)
                try:
                    await run_compilation(memory_dir, llm)
                finally:
                    await llm.close()
        except Exception:
            pass

    # Low-frequency Dream consolidation (separate counter)
    from .dream import DREAM_INTERVAL
    dream_counter = memory_dir / ".dream_counter"
    d_count = 0
    if dream_counter.is_file():
        try:
            d_count = int(dream_counter.read_text().strip())
        except (ValueError, OSError):
            d_count = 0
    d_count += 1
    dream_counter.write_text(str(d_count), encoding="utf-8")

    if d_count >= DREAM_INTERVAL:
        dream_counter.write_text("0", encoding="utf-8")
        try:
            from .dream import run_dream
            from engine.llm.model_config import resolve_llm_config, build_llm_client

            llm_cfg = resolve_llm_config(agent_dir.name)
            if llm_cfg.get("api_key"):
                llm = build_llm_client(llm_cfg)
                try:
                    await run_dream(memory_dir, llm)
                finally:
                    await llm.close()
        except Exception:
            pass

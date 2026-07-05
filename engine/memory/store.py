from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from .interface import MemoryEntry


class FileMemoryStore:
    """File-based memory store with scope-based subdirectories.

    Directory layout:
        memory/agent/<id>.md   — agent-scoped memories
        memory/project/<id>.md — project-scoped memories

    Project-scoped memories sort before agent-scoped in search results.
    Optionally backed by a SearchIndex for FTS5 + vector hybrid search.
    """

    def __init__(self, memory_dir: Path) -> None:
        self._dir = memory_dir
        self._agent_dir = memory_dir / "agent"
        self._project_dir = memory_dir / "project"
        self._agent_dir.mkdir(parents=True, exist_ok=True)
        self._project_dir.mkdir(parents=True, exist_ok=True)
        self._search_index = None  # set via attach_search_index()

    def attach_search_index(self, index) -> None:
        """Attach a SearchIndex for hybrid search (FTS5 + vector)."""
        self._search_index = index

    def _scope_dir(self, scope: str) -> Path:
        return self._project_dir if scope == "project" else self._agent_dir

    def _all_md_files(self) -> list[tuple[Path, str]]:
        """Return (path, scope) for every memory file, project first."""
        files: list[tuple[Path, str]] = []
        for f in sorted(self._project_dir.glob("*.md")):
            files.append((f, "project"))
        for f in sorted(self._agent_dir.glob("*.md")):
            files.append((f, "agent"))
        # Backward compat: root-level .md files treated as agent scope
        for f in sorted(self._dir.glob("*.md")):
            if f.parent == self._dir:
                files.append((f, "agent"))
        return files

    async def search(self, query: str) -> list[MemoryEntry]:
        # Hybrid search via SearchIndex if available
        if self._search_index:
            try:
                hits = await self._search_index.search(query)
                results: list[MemoryEntry] = []
                for hit in hits:
                    path, scope = self._find_entry_file(hit["id"])
                    if path:
                        raw = path.read_text(encoding="utf-8")
                        entry = self._parse_file(path, raw, scope or "agent")
                        if entry:
                            results.append(entry)
                if results:
                    return results
            except Exception:
                pass  # ponytail: fall through to keyword search

        # Fallback: keyword scan
        results: list[MemoryEntry] = []
        keywords = query.lower().split()
        if not keywords:
            return results
        for path, default_scope in self._all_md_files():
            content = path.read_text(encoding="utf-8")
            if any(kw in content.lower() for kw in keywords):
                entry = self._parse_file(path, content, default_scope)
                if entry:
                    results.append(entry)
        return results

    async def add(self, content: str, evidence: str, scope: str) -> MemoryEntry:
        entry_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        entry = MemoryEntry(
            id=entry_id,
            content=content,
            scope=scope,  # type: ignore[arg-type]
            evidence=evidence,
            created_at=now,
            last_accessed=now,
        )
        self._write_entry(entry)
        if self._search_index:
            try:
                await self._search_index.index_entry(entry.id, entry.content, entry.scope)
            except Exception:
                pass
        return entry

    async def update(
        self, entry_id: str, content: str | None = None, evidence: str | None = None
    ) -> bool:
        """Update an existing memory entry's content and/or evidence."""
        path, scope = self._find_entry_file(entry_id)
        if path is None:
            return False

        raw = path.read_text(encoding="utf-8")
        entry = self._parse_file(path, raw, scope or "agent")
        if entry is None:
            return False

        if content is not None:
            entry.content = content
        if evidence is not None:
            entry.evidence = evidence
        entry.last_accessed = datetime.now(timezone.utc).isoformat()

        self._write_entry(entry)
        if self._search_index:
            try:
                await self._search_index.index_entry(entry.id, entry.content, entry.scope)
            except Exception:
                pass
        return True

    async def remove(self, entry_id: str) -> bool:
        path, _ = self._find_entry_file(entry_id)
        if path is not None and path.is_file():
            path.unlink()
            if self._search_index:
                try:
                    await self._search_index.remove_entry(entry_id)
                except Exception:
                    pass
            return True
        return False

    async def list_all(self) -> list[MemoryEntry]:
        """Return all memory entries, project-scoped first."""
        entries: list[MemoryEntry] = []
        for path, default_scope in self._all_md_files():
            raw = path.read_text(encoding="utf-8")
            entry = self._parse_file(path, raw, default_scope)
            if entry:
                entries.append(entry)
        return entries

    def _find_entry_file(self, entry_id: str) -> tuple[Path | None, str | None]:
        """Locate an entry file across all scope directories."""
        for scope_dir, scope in [
            (self._project_dir, "project"),
            (self._agent_dir, "agent"),
            (self._dir, "agent"),
        ]:
            path = scope_dir / f"{entry_id}.md"
            if path.is_file():
                return path, scope
        return None, None

    def _write_entry(self, entry: MemoryEntry) -> None:
        target_dir = self._scope_dir(entry.scope)
        text = (
            f"---\n"
            f"id: {entry.id}\n"
            f"scope: {entry.scope}\n"
            f"created_at: {entry.created_at}\n"
            f"last_accessed: {entry.last_accessed}\n"
            f"---\n"
            f"{entry.content}\n\n"
            f"Evidence: {entry.evidence}\n"
        )
        (target_dir / f"{entry.id}.md").write_text(text, encoding="utf-8")

    @staticmethod
    def _parse_file(path: Path, raw: str, default_scope: str = "agent") -> MemoryEntry | None:
        """Parse a memory file with YAML frontmatter."""
        entry_id = path.stem
        scope = default_scope
        created_at = ""
        last_accessed = ""
        body = raw

        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().splitlines():
                    key, _, val = line.partition(":")
                    val = val.strip()
                    if key == "scope":
                        scope = val
                    elif key == "created_at":
                        created_at = val
                    elif key == "last_accessed":
                        last_accessed = val
                    elif key == "id":
                        entry_id = val
                body = parts[2].strip()

        # Split body from evidence
        evidence = ""
        if "\nEvidence:" in body:
            body_part, evidence = body.rsplit("\nEvidence:", 1)
            body = body_part.strip()
            evidence = evidence.strip()

        return MemoryEntry(
            id=entry_id,
            content=body,
            scope=scope,  # type: ignore[arg-type]
            evidence=evidence,
            created_at=created_at,
            last_accessed=last_accessed or created_at,
        )


# ---------------------------------------------------------------------------
# Conversation-level memory persistence
# ---------------------------------------------------------------------------

_DREAM_INTERVAL = 5  # run dream every N conversations


async def save_conversation_memory(
    employee_dir: Path, user_msg: str, reply: str, had_tools: bool
) -> None:
    """Save a memory entry after a conversation that involved tool usage."""
    if not had_tools:
        return

    import json

    memory_dir = employee_dir / "memory"
    conversations_dir = memory_dir / "conversations"
    conversations_dir.mkdir(parents=True, exist_ok=True)

    recent_file = memory_dir / "recent.jsonl"
    recent_file.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "task": user_msg[:100],
        "summary": reply[:200],
        "timestamp": now,
    }

    with open(recent_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    store = FileMemoryStore(memory_dir)

    # Attach search index for hybrid FTS5 + vector indexing
    try:
        from .search import SearchIndex, create_jina_embed_fn
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))
        from common.config_loader import resolve_llm_config
        cfg = resolve_llm_config(employee_dir.name)
        embed_fn = None
        if cfg.get("api_key") and cfg.get("base_url"):
            embed_fn = await create_jina_embed_fn(
                cfg["api_key"], cfg["base_url"], cfg.get("embedding_model", "jina-embeddings-v3"),
            )
        idx = SearchIndex(memory_dir)
        await idx.open(embed_fn)
        store.attach_search_index(idx)
    except Exception:
        pass  # ponytail: search indexing is best-effort

    await store.add(
        content=f"Task: {user_msg[:100]}\nResult: {reply[:200]}",
        evidence=f"conversation at {now}",
        scope="agent",
    )

    # Periodic dream consolidation
    counter_file = memory_dir / ".dream_counter"
    count = 0
    if counter_file.is_file():
        try:
            count = int(counter_file.read_text().strip())
        except (ValueError, OSError):
            count = 0
    count += 1
    counter_file.write_text(str(count), encoding="utf-8")

    if count >= _DREAM_INTERVAL:
        counter_file.write_text("0", encoding="utf-8")
        from .dream import DreamConsolidator
        consolidator = DreamConsolidator(store)
        await consolidator.apply()

        # ponytail: compilation is best-effort after Dream cleaning
        try:
            from .compile import run_compilation
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))
            from common.config_loader import resolve_llm_config
            from engine.llm.model_config import build_llm_client
            llm_cfg = resolve_llm_config(employee_dir.name)
            if llm_cfg.get("api_key"):
                llm = build_llm_client(llm_cfg)
                try:
                    await run_compilation(memory_dir, llm)
                finally:
                    await llm.close()
        except Exception:
            pass

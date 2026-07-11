"""Memory store — recent.jsonl as sole event source + episode FTS5 search.

FileMemoryStore is retained for backward compatibility with memory_ops.
New conversation memories are NOT written as .md entries — recent.jsonl is the
sole event source. See compile.py for the compilation pipeline.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ._files import atomic_write_text
from .interface import MemoryEntry


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Legacy FileMemoryStore — retained for memory_ops compatibility
# ---------------------------------------------------------------------------


class FileMemoryStore:
    """Legacy file-based memory store with scope-based subdirectories.

    New conversation memories are no longer written here.
    Kept temporarily for memory_ops and backward compatibility.
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

    @staticmethod
    def _entry_path(scope_dir: Path, entry_id: str) -> Path | None:
        """Return a legacy entry path only when *entry_id* is a plain filename."""
        if not entry_id or Path(entry_id).name != entry_id:
            return None

        scope_root = scope_dir.resolve()
        path = (scope_dir / f"{entry_id}.md").resolve()
        return path if path.is_relative_to(scope_root) else None

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
        path = self._entry_path(target_dir, entry.id)
        if path is None:
            raise ValueError("generated memory entry id is not a safe filename")
        atomic_write_text(path, text)
        return entry

    async def update(self, entry_id: str, content: str | None = None, evidence: str | None = None) -> bool:
        """Update a legacy .md entry."""
        if Path(entry_id).name != entry_id:
            return False
        for scope_dir, scope in [(self._project_dir, "project"), (self._agent_dir, "agent")]:
            if not scope_dir.is_dir():
                continue
            path = self._entry_path(scope_dir, entry_id)
            if path is None:
                return False
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
                target = self._entry_path(target_dir, entry.id)
                if target is None:
                    return False
                atomic_write_text(target, text)
                return True
        return False

    async def remove(self, entry_id: str) -> bool:
        if Path(entry_id).name != entry_id:
            return False
        for scope_dir in (self._project_dir, self._agent_dir):
            if not scope_dir.is_dir():
                continue
            path = self._entry_path(scope_dir, entry_id)
            if path is None:
                return False
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
                    if key == "scope":
                        scope = val
                    elif key == "created_at":
                        created_at = val
                    elif key == "last_accessed":
                        last_accessed = val
                    elif key == "id":
                        entry_id = val
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
        logger.warning("episode-memory retrieval failed", exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# Conversation-level memory persistence
# ---------------------------------------------------------------------------

_COMPILE_INTERVAL = 5
_MAX_EVENT_VALUE_CHARS = 16_000
_EPISODE_REQUEST_RE = re.compile(
    r"(?:整理|总结|归档|复盘)\s*(?:一下)?\s*(?:这段|这个|本次|当前|上述).*?(?:过程|对话|任务|工作|经历)"
    r"|\b(?:summari[sz]e|recap)\s+(?:this|the)\s+(?:process|conversation|task)\b",
    re.IGNORECASE,
)


def _bounded_event_value(value: str) -> str:
    """Keep normal conversation events intact and mark exceptional truncation."""
    if len(value) <= _MAX_EVENT_VALUE_CHARS:
        return value

    marker = "\n\n[Memory event truncated for storage]\n\n"
    available = _MAX_EVENT_VALUE_CHARS - len(marker)
    if available <= 0:
        return value[:_MAX_EVENT_VALUE_CHARS]
    head = available // 2
    tail = available - head
    return f"{value[:head]}{marker}{value[-tail:]}"


def _increment_counter(counter_file: Path, retry_threshold: int) -> int:
    count = 0
    if counter_file.is_file():
        try:
            count = int(counter_file.read_text().strip())
        except (ValueError, OSError):
            count = 0
    count = min(count + 1, retry_threshold)
    atomic_write_text(counter_file, str(count))
    return count


def _episode_topic(user_message: str) -> str | None:
    """Return a bounded topic only for an explicit episode-summary request."""
    if not _EPISODE_REQUEST_RE.search(user_message):
        return None
    topic = " ".join(user_message.split())
    return topic[:120] or None


async def _create_explicit_episode(
    agent_dir: Path,
    memory_dir: Path,
    user_message: str,
) -> None:
    topic = _episode_topic(user_message)
    if topic is None:
        return

    try:
        from .compile import _load_recent, compact_episode
        from engine.llm.model_config import LLMUsage, build_llm_client, resolve_llm_config

        related_entries = _load_recent(memory_dir)[-20:]
        if not related_entries:
            return

        llm_cfg = resolve_llm_config(usage=LLMUsage.BACKGROUND)
        if not llm_cfg.get("api_key"):
            logger.warning("episode-memory generation skipped: no LLM API key configured")
            return

        llm = build_llm_client(llm_cfg)
        try:
            await compact_episode(memory_dir, llm, topic, related_entries)
        finally:
            await llm.close()
    except Exception:
        logger.warning("explicit episode-memory generation failed", exc_info=True)


async def _run_periodic_compilation(agent_dir: Path, memory_dir: Path) -> bool:
    try:
        from .compile import run_compilation
        from engine.llm.model_config import LLMUsage, build_llm_client, resolve_llm_config

        llm_cfg = resolve_llm_config(usage=LLMUsage.BACKGROUND)
        if not llm_cfg.get("api_key"):
            logger.warning("conversation-memory compilation skipped: no LLM API key configured")
            return False

        llm = build_llm_client(llm_cfg)
        try:
            await run_compilation(memory_dir, llm, raise_on_error=True)
        finally:
            await llm.close()
        return True
    except Exception:
        logger.warning("conversation-memory compilation failed", exc_info=True)
        return False


async def _run_periodic_dream(agent_dir: Path, memory_dir: Path) -> bool:
    try:
        from .dream import run_dream
        from engine.llm.model_config import LLMUsage, build_llm_client, resolve_llm_config

        llm_cfg = resolve_llm_config(usage=LLMUsage.BACKGROUND)
        if not llm_cfg.get("api_key"):
            logger.warning("conversation-memory Dream skipped: no LLM API key configured")
            return False

        llm = build_llm_client(llm_cfg)
        try:
            report = await run_dream(memory_dir, llm)
        finally:
            await llm.close()
        if report.errors:
            logger.warning("conversation-memory Dream failed: %s", "; ".join(report.errors))
            return False
        return True
    except Exception:
        logger.warning("conversation-memory Dream consolidation failed", exc_info=True)
        return False


async def save_conversation_memory(
    agent_dir: Path, user_msg: str, reply: str, had_tools: bool
) -> None:
    """Append tool-assisted turns and periodically compile their memory views."""
    if not had_tools:
        return

    memory_dir = agent_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    recent_file = memory_dir / "recent.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "task": _bounded_event_value(user_msg),
        "summary": _bounded_event_value(reply),
        "timestamp": now,
    }

    with open(recent_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    await _create_explicit_episode(agent_dir, memory_dir, user_msg)

    # Periodic compilation (recent + durable)
    counter_file = memory_dir / ".compile_counter"
    count = _increment_counter(counter_file, _COMPILE_INTERVAL)

    if count >= _COMPILE_INTERVAL and await _run_periodic_compilation(agent_dir, memory_dir):
        atomic_write_text(counter_file, "0")

    # Low-frequency Dream consolidation (separate counter)
    from .dream import DREAM_INTERVAL
    dream_counter = memory_dir / ".dream_counter"
    d_count = _increment_counter(dream_counter, DREAM_INTERVAL)

    if d_count >= DREAM_INTERVAL and await _run_periodic_dream(agent_dir, memory_dir):
        atomic_write_text(dream_counter, "0")

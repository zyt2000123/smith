"""Memory store — recent.jsonl as sole event source + episode FTS5 search.

Provides:
  - search_relevant_memories(): FTS5 episode search for prompt injection
  - save_conversation_memory(): append events + trigger compilation/dream
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ._files import (
    atomic_write_text,
    sanitize_memory_text,
)

logger = logging.getLogger(__name__)


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
            await _sync_episode_index(idx, episodes_dir)

            hits = await idx.search(query, top_k)
            if not hits:
                return ""

            lines = ["## Relevant Episodes"]
            total_chars = 0
            episodes_root = episodes_dir.resolve()
            for hit in hits:
                ep_path = (episodes_dir / f"{hit['id']}.md").resolve()
                if not ep_path.is_relative_to(episodes_root) or not ep_path.is_file():
                    continue
                content, _, _ = sanitize_memory_text(ep_path.read_text(encoding="utf-8"))
                content = content.strip()
                if not content:
                    continue
                if total_chars + len(content) > _MAX_EPISODE_CONTEXT_CHARS:
                    continue
                lines.append(content)
                total_chars += len(content)

            return "\n\n".join(lines) if len(lines) > 1 else ""
        finally:
            await idx.close()
    except Exception:
        logger.warning("episode-memory retrieval failed", exc_info=True)
        return ""


_EPISODE_INDEX_STATE = ".index_state.json"


def _load_episode_index_state(path: Path) -> dict[str, str]:
    """Read the disposable per-file index state, rebuilding on malformed data."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict) or not all(
        isinstance(entry_id, str) and isinstance(signature, str)
        for entry_id, signature in raw.items()
    ):
        return {}
    return raw


async def _sync_episode_index(idx, episodes_dir: Path) -> None:
    """Synchronize the FTS index from current episode files.

    State is keyed per episode rather than by a global timestamp, so copied or
    restored files with an older mtime still enter the index. The state is
    disposable and is only committed after index writes and stale-row removal
    have succeeded.
    """
    state_path = episodes_dir / _EPISODE_INDEX_STATE
    previous_state = _load_episode_index_state(state_path)
    current_state: dict[str, str] = {}

    for ep in sorted(episodes_dir.glob("*.md")):
        stat = ep.stat()
        signature = f"{stat.st_mtime_ns}:{stat.st_size}"
        current_state[ep.stem] = signature
        if previous_state.get(ep.stem) != signature:
            content = ep.read_text(encoding="utf-8")
            await idx.index_entry(ep.stem, content, "episode")

    await idx.remove_missing_entries(set(current_state), "episode")

    if current_state != previous_state:
        atomic_write_text(
            state_path,
            json.dumps(current_state, ensure_ascii=False, sort_keys=True),
        )
    (episodes_dir / ".index_mtime").unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Conversation-level memory persistence
# ---------------------------------------------------------------------------

_COMPILE_INTERVAL = 5
_MAX_EVENT_VALUE_CHARS = 16_000


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


async def _run_periodic_compilation(agent_dir: Path, memory_dir: Path) -> bool:
    try:
        from .compile import run_compilation
        from engine.llm.model_config import LLMUsage, build_llm_client, resolve_llm_config

        gen_cfg = resolve_llm_config(usage=LLMUsage.BACKGROUND)
        if not gen_cfg.get("api_key"):
            logger.warning("conversation-memory compilation skipped: no LLM API key configured")
            return False

        generator = build_llm_client(gen_cfg)
        reviewer = None
        try:
            rev_cfg = resolve_llm_config(usage=LLMUsage.GATE)
            if rev_cfg.get("api_key"):
                reviewer = build_llm_client(rev_cfg)
            await run_compilation(memory_dir, generator, reviewer=reviewer, raise_on_error=True)
        finally:
            await generator.close()
            if reviewer:
                await reviewer.close()
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
        if report.errors or report.skipped:
            reason = "; ".join(report.errors) if report.errors else report.skipped
            logger.warning("conversation-memory Dream did not complete: %s", reason)
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
    bounded_task = _sanitize_event_value(user_msg)
    bounded_summary = _sanitize_event_value(reply)

    entry = {
        "task": bounded_task,
        "summary": bounded_summary,
        "timestamp": now,
    }

    with open(recent_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

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


def _sanitize_event_value(value: str) -> str:
    """Bound an event and redact values unsafe for future prompt use."""
    bounded = _bounded_event_value(value)
    cleaned, secrets_removed, injections_removed = sanitize_memory_text(bounded)
    if cleaned.strip():
        return cleaned
    if secrets_removed:
        return "[REDACTED — contained sensitive information]"
    if injections_removed:
        return "[REDACTED — contained instruction-injection patterns]"
    return bounded

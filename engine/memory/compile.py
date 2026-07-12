"""Memory compilation — recent events + durable facts + episode summaries.

Three compilation targets:
  compile_recent()   → recent.md     (last 3-7 days, budget-capped)
  compile_durable()  → durable.md    (incremental merge of stable facts)
  compact_episode()  → episodes/*.md (on an explicit user summary request)
  assemble_memory()  → combined str  (for prompt injection)

Fingerprint caching: MD5 of input keys. Same input → skip compilation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ._files import (
    MEMORY_LAYER_FILES,
    atomic_write_text,
    contains_injection,
    contains_secret,
    safe_file_in_dir,
    sanitize_memory_text,
)
from ._review import (
    MemoryCompilationError,
    _generate_and_review,
    _llm_summarize,
    _truncate_source,
)

if TYPE_CHECKING:
    from engine.llm.port import LLMPort

MAX_RECENT_CHARS = 8000
MAX_DURABLE_CHARS = 10_000
MAX_RECENT_SOURCE_CHARS = 24_000
MAX_DURABLE_SOURCE_CHARS = 16_000
MAX_EPISODE_SOURCE_CHARS = 16_000
MIN_WINDOW_DAYS = 3
MAX_WINDOW_DAYS = 7
_RECENT_REVIEW_TIMEOUT_SECONDS = 15.0
_DURABLE_REVIEW_TIMEOUT_SECONDS = 15.0

logger = logging.getLogger(__name__)


def _fingerprint(keys: list[str]) -> str:
    return hashlib.md5("|".join(keys).encode(), usedforsecurity=False).hexdigest()


def _read_fp(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return ""


def _write_fp(path: Path, fp: str) -> None:
    atomic_write_text(path, fp)


def _clear_recent_view(memory_dir: Path) -> bool:
    """Remove stale derived recent-memory artifacts without touching events."""
    removed = False
    for name in ("recent.md", ".fp_recent"):
        path = memory_dir / name
        if path.exists():
            path.unlink()
            removed = True
    return removed


def _load_recent(
    memory_dir: Path,
    *,
    from_offset: bool = False,
    offset: int | None = None,
) -> list[dict]:
    """Load events from recent.jsonl.

    When *from_offset* is True, only return entries after the last
    successfully compiled offset (stored in ``.compile_offset``).
    """
    recent = memory_dir / "recent.jsonl"
    if not recent.is_file():
        return []
    lines = recent.read_text(encoding="utf-8").strip().splitlines()
    if offset is None:
        offset = _read_offset(memory_dir) if from_offset else 0
    entries = []
    for line in lines[offset:]:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
    return entries


def _read_offset(memory_dir: Path) -> int:
    offset_file = memory_dir / ".compile_offset"
    if offset_file.is_file():
        try:
            return max(0, int(offset_file.read_text().strip()))
        except (ValueError, OSError):
            pass
    return 0


def _write_offset(memory_dir: Path, offset: int) -> None:
    atomic_write_text(memory_dir / ".compile_offset", str(offset))


def _read_durable_offset(memory_dir: Path) -> int:
    """Read the durable-specific checkpoint, falling back during migration."""
    offset_file = memory_dir / ".durable_offset"
    if offset_file.is_file():
        try:
            return max(0, int(offset_file.read_text(encoding="utf-8").strip()))
        except (ValueError, OSError):
            pass
    return _read_offset(memory_dir)


def _write_durable_offset(memory_dir: Path, offset: int) -> None:
    atomic_write_text(memory_dir / ".durable_offset", str(offset))


def _total_lines(memory_dir: Path) -> int:
    recent = memory_dir / "recent.jsonl"
    if not recent.is_file():
        return 0
    return len(recent.read_text(encoding="utf-8").strip().splitlines())


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _filter_by_time(entries: list[dict], after: datetime) -> list[dict]:
    return [
        e for e in entries
        if (_parse_ts(e.get("timestamp", "")) or datetime.min.replace(tzinfo=timezone.utc)) >= after
    ]


def _entries_to_source(
    entries: list[dict],
    summary_limit: int | None = None,
    source_limit: int | None = None,
) -> str:
    """Render events without losing normal-sized content.

    ``recent.jsonl`` keeps the durable event record. Limits here constrain only
    LLM input, and include an explicit marker when they need to apply.
    """
    lines = []
    for entry in entries:
        task, _, _ = sanitize_memory_text(str(entry.get("task", "?")))
        summary, _, _ = sanitize_memory_text(str(entry.get("summary", "?")))
        if summary_limit is not None:
            summary = _truncate_source(summary, summary_limit)
        lines.append(f"- [{str(entry.get('timestamp', '?'))[:16]}] {task}: {summary}")

    source = "\n".join(lines)
    return _truncate_source(source, source_limit) if source_limit is not None else source


# ---------------------------------------------------------------------------
# compile_recent: replace today.md + week.md with a single budget-capped view
# ---------------------------------------------------------------------------

async def compile_recent(
    memory_dir: Path,
    llm: "LLMPort",
    reviewer: "LLMPort | None" = None,
) -> bool:
    """Compile recent events into recent.md. Budget-capped, elastic 3-7 day window."""
    now = datetime.now(timezone.utc)
    # ponytail: recent.md is a rolling window — must read ALL events, not just
    # new ones. Offset is only for compile_durable's incremental merge.
    all_entries = _load_recent(memory_dir, from_offset=False)

    entries = _filter_by_time(all_entries, now - timedelta(days=MIN_WINDOW_DAYS))
    if not entries:
        entries = _filter_by_time(all_entries, now - timedelta(days=MAX_WINDOW_DAYS))
    if not entries:
        return _clear_recent_view(memory_dir)

    out = memory_dir / "recent.md"
    fp_file = memory_dir / ".fp_recent"

    fp = _fingerprint([f"{e.get('timestamp', '')}:{e.get('task', '')[:50]}" for e in entries])
    if _read_fp(fp_file) == fp and out.is_file():
        return False

    source = _entries_to_source(entries, source_limit=MAX_RECENT_SOURCE_CHARS)
    if len(source) > MAX_RECENT_CHARS:
        prompt = (
            f"Summarize recent activity into key events, grouped by date. "
            f"Max {MAX_RECENT_CHARS} chars.\n\n{source}"
        )
        if reviewer:
            try:
                summary = await asyncio.wait_for(
                    _generate_and_review(llm, reviewer, prompt, source),
                    timeout=_RECENT_REVIEW_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                # Recent memory is a derived activity view, not a source of new
                # facts. Keep it available from sanitized events even when the
                # optional LLM reviewer is unavailable or repeatedly rejects a
                # summary; durable memory remains fail-closed below.
                logger.warning(
                    "recent reviewer unavailable (%s); using sanitized event projection",
                    exc,
                    exc_info=True,
                )
                summary = _truncate_source(source, MAX_RECENT_CHARS)
        else:
            summary = await _llm_summarize(llm, prompt)
    else:
        summary = source

    if len(summary) > MAX_RECENT_CHARS:
        logger.warning("recent compilation exceeded budget (%d > %d), rejecting", len(summary), MAX_RECENT_CHARS)
        raise MemoryCompilationError("recent compilation output exceeded character budget")

    if contains_secret(summary) or contains_injection(summary):
        logger.warning("recent compilation output contains unsafe content — retrying later")
        raise MemoryCompilationError("recent compilation output contains unsafe content")

    atomic_write_text(out, f"## Recent Activity\n\n{summary}\n")
    _write_fp(fp_file, fp)
    return True


# ---------------------------------------------------------------------------
# compile_durable: incremental merge of stable facts (replace longterm+facts)
# ---------------------------------------------------------------------------

_DURABLE_MERGE_PROMPT = """\
Update the long-term memory based on new events.

Rules:
1. Keep existing facts that are still valid.
2. Add new stable information that will remain useful in future sessions.
3. When new info conflicts with old, replace the old.
4. Remove outdated, completed, or superseded content.
5. Do NOT record temporary debugging, one-off operations, or chat.
6. Do NOT record language, tone, verbosity, or interaction preferences (managed separately).
7. Do NOT repeat the same fact in different phrasings.
8. Keep the Markdown structure; add new headings if needed.
9. Keep the complete output, including headings, within {max_chars} characters.
10. Output ONLY the updated memory content.

Existing memory:
{existing}

New events:
{new_events}"""


async def compile_durable(
    memory_dir: Path,
    llm: "LLMPort",
    reviewer: "LLMPort | None" = None,
) -> bool:
    """Incrementally merge new events into durable.md."""
    durable_offset = _read_durable_offset(memory_dir)
    all_entries = _load_recent(memory_dir, offset=durable_offset)
    total = _total_lines(memory_dir)

    out = memory_dir / "durable.md"
    fp_file = memory_dir / ".fp_durable"

    fp = _fingerprint([f"{e.get('timestamp', '')}:{e.get('task', '')[:50]}" for e in all_entries])
    if _read_fp(fp_file) == fp and out.is_file():
        if not (memory_dir / ".durable_offset").is_file():
            _write_durable_offset(memory_dir, total)
        return False

    original_path = safe_file_in_dir(memory_dir, out)
    original = original_path.read_text(encoding="utf-8") if original_path else ""
    existing, _, _ = sanitize_memory_text(original)
    existing = existing.strip()
    new_source = _entries_to_source(
        all_entries,
        summary_limit=1000,
        source_limit=MAX_DURABLE_SOURCE_CHARS,
    )

    if not new_source.strip():
        return False

    merge_prompt = _DURABLE_MERGE_PROMPT.format(
        existing=existing or "(empty — first compilation)",
        new_events=new_source,
        max_chars=MAX_DURABLE_CHARS,
    )
    if reviewer:
        summary = await asyncio.wait_for(
            _generate_and_review(llm, reviewer, merge_prompt, new_source),
            timeout=_DURABLE_REVIEW_TIMEOUT_SECONDS,
        )
    else:
        summary = await asyncio.wait_for(
            _llm_summarize(llm, merge_prompt),
            timeout=_DURABLE_REVIEW_TIMEOUT_SECONDS,
        )

    summary = summary.strip()
    if not summary:
        logger.warning("durable compilation output was empty — keeping existing memory")
        raise MemoryCompilationError("durable compilation output was empty")
    if contains_secret(summary) or contains_injection(summary):
        logger.warning("durable compilation output contains unsafe content — keeping existing memory")
        raise MemoryCompilationError("durable compilation output contains unsafe content")

    durable = f"## Durable Memory\n\n{summary}\n"
    if len(durable) > MAX_DURABLE_CHARS:
        logger.warning("durable memory exceeded %s characters; rejecting", MAX_DURABLE_CHARS)
        raise MemoryCompilationError("durable compilation output exceeded character budget")
    if original and original != durable:
        atomic_write_text(out.with_name("durable.md.bak"), original)
    atomic_write_text(out, durable)
    _write_fp(fp_file, fp)
    _write_durable_offset(memory_dir, total)
    return True


# ---------------------------------------------------------------------------
# compact_episode: compress a completed topic into an episode file
# ---------------------------------------------------------------------------

async def compact_episode(
    memory_dir: Path,
    llm: "LLMPort",
    topic: str,
    related_entries: list[dict],
    reviewer: "LLMPort | None" = None,
) -> Path | None:
    """Generate an episode summary for a completed topic. Returns the file path."""
    if not related_entries:
        return None
    if contains_secret(topic) or contains_injection(topic):
        logger.warning("episode topic contains unsafe content — skipping write")
        return None

    episodes_dir = memory_dir / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", topic.lower()).strip("-_")[:60]
    if not slug:
        return None

    episodes_root = episodes_dir.resolve()
    out = (episodes_dir / f"{slug}.md").resolve()
    if not out.is_relative_to(episodes_root):
        raise ValueError("episode path escaped its storage directory")

    source = _entries_to_source(
        related_entries[-20:],
        summary_limit=1200,
        source_limit=MAX_EPISODE_SOURCE_CHARS,
    )
    prompt = (
        f"Write a concise episode summary for the topic: {topic}\n\n"
        f"Include: background, process, key decisions, and outcome.\n"
        f"Max 800 chars.\n\n{source}"
    )
    if reviewer:
        summary = await _generate_and_review(llm, reviewer, prompt, source)
    else:
        summary = await _llm_summarize(llm, prompt)

    _MAX_EPISODE_CHARS = 800
    if len(summary) > _MAX_EPISODE_CHARS:
        logger.warning("episode summary exceeded %s characters — skipping write", _MAX_EPISODE_CHARS)
        raise MemoryCompilationError("episode summary exceeded character budget")

    if contains_secret(summary):
        logger.warning("episode output contains secrets — skipping write")
        return None
    if contains_injection(summary):
        logger.warning("episode output contains injection markers — skipping write")
        return None

    atomic_write_text(out, f"# {topic}\n\n{summary}\n")
    return out


# ---------------------------------------------------------------------------
# assemble_memory: combine compiled layers for prompt injection
# ---------------------------------------------------------------------------

def assemble_memory(memory_dir: Path) -> str:
    """Combine durable + recent into a single memory block for prompt injection.

    Episodes are not included here — they should be retrieved via FTS5
    based on the current query and injected separately.
    """
    sections = []

    for name in MEMORY_LAYER_FILES:
        path = safe_file_in_dir(memory_dir, memory_dir / name)
        if path is not None:
            content, _, _ = sanitize_memory_text(path.read_text(encoding="utf-8"))
            content = content.strip()
            if content:
                sections.append(content)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# run_compilation: entry point called by store.py after Dream
# ---------------------------------------------------------------------------

async def run_compilation(
    memory_dir: Path,
    llm: "LLMPort",
    *,
    reviewer: "LLMPort | None" = None,
    raise_on_error: bool = False,
    allow_partial_progress: bool = False,
) -> dict:
    """Run compilation, optionally surfacing failures for retry control.

    Lifecycle maintenance may allow one layer to succeed while another layer
    remains pending review. Direct callers retain strict failure semantics by
    default.
    """
    memory_dir.mkdir(parents=True, exist_ok=True)
    total = _total_lines(memory_dir)
    results = {"recent": False, "durable": False}
    errors: list[str] = []
    try:
        results["recent"] = await compile_recent(memory_dir, llm, reviewer)
    except Exception:
        logger.warning("recent-memory compilation failed", exc_info=True)
        errors.append("recent-memory compilation failed")
    try:
        results["durable"] = await compile_durable(memory_dir, llm, reviewer)
    except Exception:
        logger.warning("durable-memory compilation failed", exc_info=True)
        errors.append("durable-memory compilation failed")
    if not errors and (results["recent"] or results["durable"]):
        _write_offset(memory_dir, total)
    # A successful layer is useful progress even when a later layer failed.
    # Only lifecycle callers opt into resetting their retry counter here; the
    # direct API keeps its strict raise-on-error behavior by default.
    if (
        errors
        and raise_on_error
        and not (allow_partial_progress and (results["recent"] or results["durable"]))
    ):
        raise RuntimeError("; ".join(errors))
    return results

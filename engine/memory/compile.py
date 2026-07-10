"""Memory compilation — recent events + durable facts + episode summaries.

Three compilation targets:
  compile_recent()   → recent.md     (last 7-14 days, budget-capped)
  compile_durable()  → durable.md    (incremental merge of stable facts)
  compact_episode()  → episodes/*.md (on topic completion, not automatic)
  assemble_memory()  → combined str  (for prompt injection)

Fingerprint caching: MD5 of input keys. Same input → skip compilation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ._files import atomic_write_text

if TYPE_CHECKING:
    from engine.llm.client import LLMClient

MAX_RECENT_CHARS = 8000
MAX_DURABLE_CHARS = 10_000
MIN_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 14

logger = logging.getLogger(__name__)


def _fingerprint(keys: list[str]) -> str:
    return hashlib.md5("|".join(keys).encode()).hexdigest()


def _read_fp(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return ""


def _write_fp(path: Path, fp: str) -> None:
    atomic_write_text(path, fp)


def _load_recent(memory_dir: Path) -> list[dict]:
    recent = memory_dir / "recent.jsonl"
    if not recent.is_file():
        return []
    entries = []
    for line in recent.read_text(encoding="utf-8").strip().splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


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


def _entries_to_source(entries: list[dict], summary_limit: int = 120) -> str:
    return "\n".join(
        f"- [{e.get('timestamp', '?')[:16]}] {e.get('task', '?')}: "
        f"{e.get('summary', '?')[:summary_limit]}"
        for e in entries
    )


async def _llm_summarize(llm: "LLMClient", prompt: str) -> str:
    resp = await llm.chat([
        {"role": "system", "content": (
            "You are a memory compiler. Extract ONLY user-relevant information: "
            "who the user is, what they care about, preferences, recurring patterns. "
            "Do NOT include file names, tool calls, command outputs, or execution details. "
            "Output concise bullet points in the same language as the input, "
            "within the character limit stated in the task."
        )},
        {"role": "user", "content": prompt},
    ])
    return resp.text.strip()


# ---------------------------------------------------------------------------
# compile_recent: replace today.md + week.md with a single budget-capped view
# ---------------------------------------------------------------------------

async def compile_recent(memory_dir: Path, llm: "LLMClient") -> bool:
    """Compile recent events into recent.md. Budget-capped, elastic 7-14 day window."""
    now = datetime.now(timezone.utc)
    all_entries = _load_recent(memory_dir)

    entries = _filter_by_time(all_entries, now - timedelta(days=MIN_WINDOW_DAYS))
    if not entries:
        entries = _filter_by_time(all_entries, now - timedelta(days=MAX_WINDOW_DAYS))
    if not entries:
        return False

    out = memory_dir / "recent.md"
    fp_file = memory_dir / ".fp_recent"

    fp = _fingerprint([f"{e.get('timestamp', '')}:{e.get('task', '')[:50]}" for e in entries])
    if _read_fp(fp_file) == fp:
        return False

    source = _entries_to_source(entries)
    if len(source) > MAX_RECENT_CHARS:
        summary = await _llm_summarize(
            llm,
            f"Summarize recent activity into key events, grouped by date. "
            f"Max {MAX_RECENT_CHARS} chars.\n\n{source}",
        )
    else:
        summary = source

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


async def compile_durable(memory_dir: Path, llm: "LLMClient") -> bool:
    """Incrementally merge new events into durable.md."""
    all_entries = _load_recent(memory_dir)

    out = memory_dir / "durable.md"
    fp_file = memory_dir / ".fp_durable"

    fp = _fingerprint([f"{e.get('timestamp', '')}:{e.get('task', '')[:50]}" for e in all_entries[-30:]])
    if _read_fp(fp_file) == fp:
        return False

    existing = out.read_text(encoding="utf-8").strip() if out.is_file() else ""
    new_source = _entries_to_source(all_entries[-20:], 100)

    if not new_source.strip():
        return False

    summary = await _llm_summarize(llm, _DURABLE_MERGE_PROMPT.format(
        existing=existing or "(empty — first compilation)",
        new_events=new_source,
        max_chars=MAX_DURABLE_CHARS,
    ))

    durable = f"## Durable Memory\n\n{summary}\n"
    if len(durable) > MAX_DURABLE_CHARS:
        logger.warning("durable memory exceeded %s characters; truncating", MAX_DURABLE_CHARS)
        durable = durable[:MAX_DURABLE_CHARS].rstrip()
        if len(durable) < MAX_DURABLE_CHARS:
            durable += "\n"
    atomic_write_text(out, durable)
    _write_fp(fp_file, fp)
    return True


# ---------------------------------------------------------------------------
# compact_episode: compress a completed topic into an episode file
# ---------------------------------------------------------------------------

async def compact_episode(
    memory_dir: Path,
    llm: "LLMClient",
    topic: str,
    related_entries: list[dict],
) -> Path | None:
    """Generate an episode summary for a completed topic. Returns the file path."""
    if not related_entries:
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

    source = _entries_to_source(related_entries)
    summary = await _llm_summarize(llm, (
        f"Write a concise episode summary for the topic: {topic}\n\n"
        f"Include: background, process, key decisions, and outcome.\n"
        f"Max 800 chars.\n\n{source}"
    ))

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

    for name in ("durable.md", "recent.md"):
        path = memory_dir / name
        if path.is_file():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                sections.append(content)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# run_compilation: entry point called by store.py after Dream
# ---------------------------------------------------------------------------

async def run_compilation(memory_dir: Path, llm: "LLMClient") -> dict:
    """Run compilation pipeline. Returns {layer: recompiled_bool}."""
    memory_dir.mkdir(parents=True, exist_ok=True)
    results = {"recent": False, "durable": False}
    try:
        results["recent"] = await compile_recent(memory_dir, llm)
    except Exception:
        logger.warning("recent-memory compilation failed", exc_info=True)
    try:
        results["durable"] = await compile_durable(memory_dir, llm)
    except Exception:
        logger.warning("durable-memory compilation failed", exc_info=True)
    return results

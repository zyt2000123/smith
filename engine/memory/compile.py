"""Memory compilation pipeline — LLM-based distillation with fingerprint caching.

Four independent layers, each producing a .md file:
  compile_today()    → today.md     (today's sessions → 3-5 event summaries)
  compile_week()     → week.md      (7-day window → theme overview)
  compile_longterm() → longterm.md  (fold week into long-term accumulation)
  compile_facts()    → facts.md     (extract durable facts from recent 30 days)
  assemble_memory()  → combined str (for prompt injection)

Fingerprint caching: MD5 of input keys. Same input → skip compilation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.llm.client import LLMClient


def _fingerprint(keys: list[str]) -> str:
    return hashlib.md5("|".join(keys).encode()).hexdigest()


def _read_fp(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return ""


def _write_fp(path: Path, fp: str) -> None:
    path.write_text(fp, encoding="utf-8")


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
    result = []
    for e in entries:
        t = _parse_ts(e.get("timestamp", ""))
        if t and t >= after:
            result.append(e)
    return result


async def _llm_summarize(llm: LLMClient, prompt: str) -> str:
    resp = await llm.chat([
        {"role": "system", "content": (
            "You are a memory compiler. Extract ONLY user-relevant information: "
            "who the user is, what they care about, preferences, recurring patterns. "
            "Do NOT include file names, tool calls, command outputs, or execution details. "
            "Output concise bullet points in the same language as the input. Max 400 chars."
        )},
        {"role": "user", "content": prompt},
    ])
    return resp.text.strip()


def _entries_to_source(entries: list[dict], summary_limit: int = 120) -> str:
    return "\n".join(
        f"- [{e.get('timestamp', '?')[:16]}] {e.get('task', '?')}: "
        f"{e.get('summary', '?')[:summary_limit]}"
        for e in entries
    )


async def compile_today(memory_dir: Path, llm: LLMClient) -> bool:
    """Compile today's conversations into today.md. Returns True if recompiled."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_entries = _filter_by_time(_load_recent(memory_dir), today_start)

    out = memory_dir / "today.md"
    fp_file = memory_dir / ".fp_today"

    if not today_entries:
        out.write_text("## Today\n\n_No conversations today._\n", encoding="utf-8")
        return False

    fp = _fingerprint([f"{e.get('timestamp', '')}:{e.get('task', '')[:50]}" for e in today_entries])
    if _read_fp(fp_file) == fp:
        return False

    summary = await _llm_summarize(
        llm, f"Summarize today's conversations into 3-5 key events:\n\n{_entries_to_source(today_entries)}"
    )
    out.write_text(f"## Today\n\n{summary}\n", encoding="utf-8")
    _write_fp(fp_file, fp)
    return True


async def compile_week(memory_dir: Path, llm: LLMClient) -> bool:
    """Compile past 7 days into week.md."""
    week_entries = _filter_by_time(
        _load_recent(memory_dir),
        datetime.now(timezone.utc) - timedelta(days=7),
    )

    out = memory_dir / "week.md"
    fp_file = memory_dir / ".fp_week"

    if not week_entries:
        out.write_text("## This Week\n\n_No recent activity._\n", encoding="utf-8")
        return False

    fp = _fingerprint([f"{e.get('timestamp', '')}:{e.get('task', '')[:50]}" for e in week_entries])
    if _read_fp(fp_file) == fp:
        return False

    summary = await _llm_summarize(
        llm, f"Identify 3-5 recurring themes from this week's work:\n\n{_entries_to_source(week_entries, 100)}"
    )
    out.write_text(f"## This Week\n\n{summary}\n", encoding="utf-8")
    _write_fp(fp_file, fp)
    return True


async def compile_longterm(memory_dir: Path, llm: LLMClient) -> bool:
    """Fold week.md into longterm.md (accumulative)."""
    week_file = memory_dir / "week.md"
    out = memory_dir / "longterm.md"
    fp_file = memory_dir / ".fp_longterm"

    if not week_file.is_file():
        return False
    week_content = week_file.read_text(encoding="utf-8").strip()
    if not week_content or "_No recent" in week_content:
        return False

    fp = _fingerprint([week_content])
    if _read_fp(fp_file) == fp:
        return False

    existing = out.read_text(encoding="utf-8").strip() if out.is_file() else ""

    summary = await _llm_summarize(llm, (
        f"Merge this week's summary into long-term memory. "
        f"Keep only durable patterns and preferences. Remove duplicates. Max 600 chars.\n\n"
        f"Existing:\n{existing or '(empty)'}\n\nThis week:\n{week_content}"
    ))
    out.write_text(f"## Long-term Memory\n\n{summary}\n", encoding="utf-8")
    _write_fp(fp_file, fp)
    return True


async def compile_facts(memory_dir: Path, llm: LLMClient) -> bool:
    """Extract durable facts from recent 30 days."""
    recent = _filter_by_time(
        _load_recent(memory_dir),
        datetime.now(timezone.utc) - timedelta(days=30),
    )[-50:]

    out = memory_dir / "facts.md"
    fp_file = memory_dir / ".fp_facts"

    if not recent:
        return False

    fp = _fingerprint([f"{e.get('timestamp', '')}:{e.get('task', '')[:50]}" for e in recent])
    if _read_fp(fp_file) == fp:
        return False

    existing = out.read_text(encoding="utf-8").strip() if out.is_file() else ""

    summary = await _llm_summarize(llm, (
        f"Extract durable facts about the user. Carry forward still-valid facts. "
        f"Facts = who they are, projects, preferences, tech stack. "
        f"NOT session details. Max 500 chars.\n\n"
        f"Previous facts:\n{existing or '(none)'}\n\n"
        f"Recent:\n{_entries_to_source(recent, 100)}"
    ))
    out.write_text(f"## Key Facts\n\n{summary}\n", encoding="utf-8")
    _write_fp(fp_file, fp)
    return True


def assemble_memory(memory_dir: Path) -> str:
    """Combine compiled layers into a single memory block for prompt injection.

    Falls back to empty string if no compiled files exist yet.
    """
    sections = []
    for name in ("facts.md", "longterm.md", "week.md", "today.md"):
        path = memory_dir / name
        if path.is_file():
            content = path.read_text(encoding="utf-8").strip()
            if content and "_No " not in content:
                sections.append(content)
    return "\n\n".join(sections)


async def run_compilation(memory_dir: Path, llm: LLMClient) -> dict:
    """Run full compilation pipeline. Returns {layer: recompiled_bool}."""
    memory_dir.mkdir(parents=True, exist_ok=True)
    return {
        "today": await compile_today(memory_dir, llm),
        "week": await compile_week(memory_dir, llm),
        "longterm": await compile_longterm(memory_dir, llm),
        "facts": await compile_facts(memory_dir, llm),
    }

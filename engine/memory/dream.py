"""Dream — low-frequency memory consolidation for durable.md.

Runs less frequently than compile_durable (every ~50 conversations or daily).
While compile_durable is an online incremental writer, Dream is a conservative
offline janitor that cleans up what incremental compilation accumulates.

Steps:
  1. Sanitize: regex-scan durable.md for leaked secrets, remove matching lines
  2. Consolidate: LLM pass to compress redundancy, merge near-synonyms,
     remove stale facts, without introducing new information
  3. Report what changed
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ._files import atomic_write_text

if TYPE_CHECKING:
    from engine.llm.client import LLMClient


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Secret patterns — lines matching these are unsafe to keep
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)password\s*[:=]\s*\S+"),
    re.compile(r"(?i)secret\s*[:=]\s*\S+"),
    re.compile(r"(?i)token\s*[:=]\s*[A-Za-z0-9_\-\.]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"),
]


def _contains_secret(text: str) -> bool:
    return any(p.search(text) for p in _SECRET_PATTERNS)


def _sanitize_lines(content: str) -> tuple[str, int]:
    """Remove lines containing secrets. Returns (cleaned, count_removed)."""
    lines = content.splitlines()
    clean = []
    removed = 0
    for line in lines:
        if _contains_secret(line):
            removed += 1
        else:
            clean.append(line)
    return "\n".join(clean), removed


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class DreamReport:
    secrets_removed: int = 0
    consolidated: bool = False
    skipped: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM consolidation prompt
# ---------------------------------------------------------------------------

_CONSOLIDATE_PROMPT = """\
You are maintaining long-term memory. Clean up the content below.

Rules:
1. Do NOT introduce any new facts not present in the input.
2. Do NOT modify recent.jsonl (not your concern).
3. Do NOT record or modify interaction preferences (language, tone, verbosity).
4. Merge duplicate or near-synonym expressions into one.
5. Remove facts that are clearly outdated or superseded by newer statements.
6. Keep specific project names, key decisions, and current status.
7. Only generalize into a pattern if 3+ separate facts support it.
8. Do NOT turn a one-time action into a long-term habit.
9. Preserve the Markdown heading structure.
10. Output ONLY the cleaned content — no commentary.

Content to consolidate:
{content}"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

DREAM_INTERVAL = 50


async def run_dream(memory_dir: Path, llm: "LLMClient") -> DreamReport:
    """Run Dream consolidation on durable.md. Returns a report."""
    report = DreamReport()
    durable_path = memory_dir / "durable.md"

    if not durable_path.is_file():
        report.skipped = "no durable.md"
        return report

    original_content = durable_path.read_text(encoding="utf-8")
    content = original_content.strip()
    if not content or len(content) < 100:
        report.skipped = "durable.md too short to consolidate"
        return report

    # Step 1: sanitize secrets (fast, no LLM)
    content, secrets_removed = _sanitize_lines(content)
    report.secrets_removed = secrets_removed

    # Step 2: LLM consolidation
    try:
        resp = await llm.chat([
            {"role": "system", "content": "You are a memory janitor. Be conservative — only clean, never add."},
            {"role": "user", "content": _CONSOLIDATE_PROMPT.format(content=content)},
        ])
        consolidated = resp.text.strip()

        if consolidated and len(consolidated) > 50:
            atomic_write_text(durable_path.with_name("durable.md.bak"), original_content)
            atomic_write_text(durable_path, consolidated + "\n")
            report.consolidated = True
        else:
            report.skipped = "LLM returned insufficient output"
    except Exception as e:
        report.errors.append(f"consolidation: {type(e).__name__}: {e}")
        logger.warning("dream consolidation failed", exc_info=True)

    return report

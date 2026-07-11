"""Dream — low-frequency global memory review and log cleanup.

Runs every ~50 conversations. Responsibilities:
  1. Sanitize: regex-scan all memory layers for leaked secrets
  2. Cross-layer review: check consistency across recent/durable/episodes
  3. Consolidate: LLM pass to compress redundancy in durable.md
  4. Log cleanup: truncate recent.jsonl entries before the compile offset
  5. Report what changed
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ._files import atomic_write_text, contains_secret

if TYPE_CHECKING:
    from engine.llm.port import LLMPort


logger = logging.getLogger(__name__)


def _sanitize_lines(content: str) -> tuple[str, int]:
    """Remove lines containing secrets. Returns (cleaned, count_removed)."""
    lines = content.splitlines()
    clean = []
    removed = 0
    for line in lines:
        if contains_secret(line):
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
    log_lines_cleaned: int = 0
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


async def run_dream(memory_dir: Path, llm: "LLMPort") -> DreamReport:
    """Run Dream global review on all memory layers. Returns a report."""
    report = DreamReport()

    _sanitize_all_layers(memory_dir, report)

    await _consolidate_durable(memory_dir, llm, report)

    _cleanup_log(memory_dir, report)

    return report


def _sanitize_all_layers(memory_dir: Path, report: DreamReport) -> None:
    """Scan all memory files for secrets."""
    total_removed = 0
    for md_file in _all_memory_files(memory_dir):
        content = md_file.read_text(encoding="utf-8")
        cleaned, removed = _sanitize_lines(content)
        if removed:
            atomic_write_text(md_file, cleaned)
            total_removed += removed
    report.secrets_removed = total_removed


def _all_memory_files(memory_dir: Path) -> list[Path]:
    """Collect all .md files across memory layers."""
    files = []
    for name in ("durable.md", "recent.md"):
        path = memory_dir / name
        if path.is_file():
            files.append(path)
    episodes_dir = memory_dir / "episodes"
    if episodes_dir.is_dir():
        files.extend(sorted(episodes_dir.glob("*.md")))
    return files


async def _consolidate_durable(
    memory_dir: Path,
    llm: "LLMPort",
    report: DreamReport,
) -> None:
    durable_path = memory_dir / "durable.md"

    if not durable_path.is_file():
        report.skipped = "no durable.md"
        return

    original_content = durable_path.read_text(encoding="utf-8")
    content = original_content.strip()
    if not content or len(content) < 100:
        report.skipped = "durable.md too short to consolidate"
        return

    content, secrets_removed = _sanitize_lines(content)
    report.secrets_removed += secrets_removed

    try:
        resp = await llm.chat([
            {"role": "system", "content": "You are a memory janitor. Be conservative — only clean, never add."},
            {"role": "user", "content": _CONSOLIDATE_PROMPT.format(content=content)},
        ])
        consolidated = resp.text.strip()

        if consolidated and len(consolidated) > 50:
            if contains_secret(consolidated):
                logger.warning("dream consolidation output still contains secrets — keeping original")
                report.errors.append("consolidation output contained secrets")
            else:
                atomic_write_text(durable_path.with_name("durable.md.bak"), original_content)
                atomic_write_text(durable_path, consolidated + "\n")
                report.consolidated = True
        else:
            report.skipped = "LLM returned insufficient output"
    except Exception as e:
        report.errors.append(f"consolidation: {type(e).__name__}: {e}")
        logger.warning("dream consolidation failed", exc_info=True)


def _cleanup_log(memory_dir: Path, report: DreamReport) -> None:
    """Truncate recent.jsonl entries before the compile offset.

    Only cleans if both recent.md and durable.md exist — proving
    compilation has run successfully at least once.
    """
    recent = memory_dir / "recent.jsonl"
    offset_file = memory_dir / ".compile_offset"

    if not recent.is_file() or not offset_file.is_file():
        return

    if not (memory_dir / "recent.md").is_file() or not (memory_dir / "durable.md").is_file():
        return

    try:
        offset = max(0, int(offset_file.read_text().strip()))
    except (ValueError, OSError):
        return

    if offset <= 0:
        return

    lines = recent.read_text(encoding="utf-8").strip().splitlines()
    if offset >= len(lines):
        atomic_write_text(recent, "")
        report.log_lines_cleaned = len(lines)
    else:
        remaining = lines[offset:]
        atomic_write_text(recent, "\n".join(remaining) + "\n")
        report.log_lines_cleaned = offset

    if report.log_lines_cleaned > 0:
        atomic_write_text(offset_file, "0")

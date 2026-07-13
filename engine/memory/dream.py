"""Dream — low-frequency global memory review and log cleanup.

Runs every ~50 conversations. Responsibilities:
  1. Sanitize: regex-scan all memory layers for leaked secrets and injection markers
  2. Consolidate: LLM pass to compress redundancy in durable.md
  3. Review: require policy-based reviewer approval before replacement
  4. Log cleanup: truncate recent.jsonl entries before the compile offset
  5. Report what changed
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .compile import (
    MAX_DURABLE_CHARS,
    MAX_WINDOW_DAYS,
    _read_durable_offset,
    _read_offset,
)
from ._files import (
    MEMORY_LAYER_FILES,
    atomic_write_text,
    contains_injection,
    contains_secret,
    safe_file_in_dir,
    safe_markdown_files,
    sanitize_memory_text,
)
from ._review import (
    MemoryCompilationError,
    _generate_and_review_result,
)
from .history import append_memory_history
from .policy import (
    MemoryPolicyError,
    load_memory_policy,
    resolve_view_path,
    validate_rendered_view,
)

if TYPE_CHECKING:
    from engine.llm.port import LLMPort


logger = logging.getLogger(__name__)
_MEMORY_POLICY = load_memory_policy()


def _sanitize_lines(content: str) -> tuple[str, int, int]:
    """Remove secret and instruction-like lines with separate audit counts."""
    return sanitize_memory_text(content)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class DreamReport:
    secrets_removed: int = 0
    injection_lines_removed: int = 0
    consolidated: bool = False
    log_lines_cleaned: int = 0
    skipped: str = ""
    errors: list[str] = field(default_factory=list)


def dream_report_completed(report: DreamReport) -> bool:
    """Return whether Dream maintenance should reset its retry counter."""
    if report.errors:
        return False
    benign_skips = {
        "",
        "no durable.md",
        "durable.md too short to consolidate",
        "durable.md already consolidated",
    }
    return report.skipped in benign_skips


# ---------------------------------------------------------------------------
# LLM consolidation prompt
# ---------------------------------------------------------------------------

_CONSOLIDATE_PROMPT = """\
Consolidate the complete durable-memory view below.

Canonical MemoryPolicy:
{dream_policy}

Current accepted Markdown (the only factual source):
{content}

Output only the complete Markdown document beginning with `# {title}`.
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

DREAM_INTERVAL = 50


async def run_dream(
    memory_dir: Path,
    llm: "LLMPort",
    reviewer: "LLMPort | None" = None,
) -> DreamReport:
    """Run Dream global review on all memory layers. Returns a report."""
    report = DreamReport()

    _sanitize_all_layers(memory_dir, report)

    await _consolidate_durable(memory_dir, llm, report, reviewer=reviewer)

    _cleanup_log(memory_dir, report)

    return report


def _sanitize_all_layers(memory_dir: Path, report: DreamReport) -> None:
    """Scan all memory files for secrets and instruction-like content."""
    secrets_removed = 0
    injections_removed = 0
    for md_file in _all_memory_files(memory_dir):
        content = md_file.read_text(encoding="utf-8")
        cleaned, file_secrets, file_injections = _sanitize_lines(content)
        if file_secrets or file_injections:
            atomic_write_text(md_file, cleaned)
            secrets_removed += file_secrets
            injections_removed += file_injections
    report.secrets_removed = secrets_removed
    report.injection_lines_removed = injections_removed


def _all_memory_files(memory_dir: Path) -> list[Path]:
    """Collect all .md files across memory layers."""
    files = []
    try:
        context_path = resolve_view_path(_MEMORY_POLICY, memory_dir.parent, "context")
        safe_context = safe_file_in_dir(memory_dir.parent, context_path)
        if safe_context is not None:
            files.append(safe_context)
    except MemoryPolicyError:
        logger.warning("skipping context.md outside the Agent profile")
    for name in MEMORY_LAYER_FILES:
        path = memory_dir / name
        safe_path = safe_file_in_dir(memory_dir, path)
        if safe_path is not None:
            files.append(safe_path)
    episodes_dir = memory_dir / "episodes"
    files.extend(safe_markdown_files(episodes_dir))
    return files


async def _consolidate_durable(
    memory_dir: Path,
    llm: "LLMPort",
    report: DreamReport,
    *,
    reviewer: "LLMPort | None" = None,
) -> None:
    policy = _MEMORY_POLICY
    try:
        durable_target = resolve_view_path(policy, memory_dir.parent, "durable")
    except MemoryPolicyError:
        report.skipped = "no durable.md"
        return
    durable_path = safe_file_in_dir(memory_dir, durable_target)

    if durable_path is None:
        report.skipped = "no durable.md"
        return

    original_content = durable_path.read_text(encoding="utf-8")
    content = original_content.strip()
    if not content or len(content) < 100:
        report.skipped = "durable.md too short to consolidate"
        return

    content, secrets_removed, injections_removed = _sanitize_lines(content)
    report.secrets_removed += secrets_removed
    report.injection_lines_removed += injections_removed

    consolidation_prompt = _CONSOLIDATE_PROMPT.format(
        dream_policy=policy.instructions_for("durable", role="dream"),
        content=content,
        title=policy.view("durable").title,
    )
    system_prompt = (
        "You are Smith's durable-memory consolidator. Follow the supplied "
        "canonical MemoryPolicy exactly and never add facts."
    )
    review_rounds = 0

    try:
        if reviewer is None:
            raise MemoryCompilationError(
                "Dream consolidation requires a reviewer model"
            )
        outcome = await _generate_and_review_result(
            llm,
            reviewer,
            consolidation_prompt,
            content,
            system_prompt=system_prompt,
            target_view="durable.md Dream consolidation",
            review_policy=policy.instructions_for("durable", role="dream"),
        )
        consolidated = outcome.text
        review_rounds = outcome.rounds

        consolidated = consolidated.strip() + "\n" if consolidated.strip() else ""
        if not consolidated or len(consolidated) <= 50:
            raise MemoryCompilationError("LLM returned insufficient output")
        validate_rendered_view(policy, "durable", consolidated)
        if contains_secret(consolidated) or contains_injection(consolidated):
            raise MemoryCompilationError("consolidation output contained unsafe content")
        if len(consolidated) > MAX_DURABLE_CHARS:
            raise MemoryCompilationError("consolidation output exceeded character budget")

        accepted = original_content.strip() + "\n"
        if consolidated == accepted:
            report.skipped = "durable.md already consolidated"
            append_memory_history(
                memory_dir,
                target="dream",
                policy_version=policy.version,
                status="unchanged",
                old_text=original_content,
                new_text=consolidated,
                review_rounds=review_rounds,
            )
            return

        atomic_write_text(durable_path.with_name("durable.md.bak"), original_content)
        atomic_write_text(durable_path, consolidated)
        append_memory_history(
            memory_dir,
            target="dream",
            policy_version=policy.version,
            status="written",
            old_text=original_content,
            new_text=consolidated,
            review_rounds=review_rounds,
        )
        report.consolidated = True
    except (MemoryCompilationError, MemoryPolicyError) as e:
        review_rounds = max(
            review_rounds,
            getattr(e, "review_rounds", 0),
        )
        append_memory_history(
            memory_dir,
            target="dream",
            policy_version=policy.version,
            status="rejected",
            old_text=original_content,
            review_rounds=review_rounds,
            error=f"{type(e).__name__}: {e}",
        )
        report.errors.append(f"consolidation: {e}")
        logger.warning("dream consolidation review rejected output: %s", e)
    except Exception as e:
        append_memory_history(
            memory_dir,
            target="dream",
            policy_version=policy.version,
            status="failed",
            old_text=original_content,
            review_rounds=review_rounds,
            error=f"{type(e).__name__}: {e}",
        )
        report.errors.append(f"consolidation: {type(e).__name__}: {e}")
        logger.warning("dream consolidation failed", exc_info=True)


def _cleanup_log(memory_dir: Path, report: DreamReport) -> None:
    """Truncate recent.jsonl entries that are both before every compile
    checkpoint AND older than MAX_WINDOW_DAYS, preserving the rolling window.
    """
    recent = memory_dir / "recent.jsonl"
    offset_file = memory_dir / ".compile_offset"

    if not recent.is_file() or not offset_file.is_file():
        return

    if safe_file_in_dir(memory_dir, memory_dir / "durable.md") is None:
        return

    compile_offset = _read_offset(memory_dir)
    durable_offset = _read_durable_offset(memory_dir)
    # Never delete lines the durable merge has not consumed yet.
    offset = min(compile_offset, durable_offset)

    if offset <= 0:
        return

    lines = recent.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_WINDOW_DAYS)).isoformat()
    safe_offset = 0
    for i, line in enumerate(lines[:offset]):
        try:
            entry = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            safe_offset = i + 1
            continue
        if not isinstance(entry, dict):
            safe_offset = i + 1
            continue
        ts = entry.get("timestamp", "")
        if ts and ts < cutoff:
            safe_offset = i + 1

    if safe_offset <= 0:
        return

    remaining = lines[safe_offset:]
    atomic_write_text(recent, "\n".join(remaining) + "\n" if remaining else "")
    report.log_lines_cleaned = safe_offset

    atomic_write_text(offset_file, str(max(0, compile_offset - safe_offset)))

    durable_offset_file = memory_dir / ".durable_offset"
    if durable_offset_file.is_file():
        atomic_write_text(
            durable_offset_file,
            str(max(0, durable_offset - safe_offset)),
        )

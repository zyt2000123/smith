"""Append-only audit history for automatic memory changes."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ._files import sanitize_memory_text

logger = logging.getLogger(__name__)


def append_memory_history(
    memory_dir: Path,
    *,
    target: str,
    policy_version: int,
    status: str,
    old_text: str = "",
    new_text: str = "",
    review_rounds: int = 0,
    error: str | None = None,
) -> bool:
    """Append one sanitized compile/review/write outcome without blocking memory."""
    cleaned_error: str | None = None
    if error:
        cleaned_error, _, _ = sanitize_memory_text(error)
        cleaned_error = cleaned_error.strip()[:500] or "redacted error"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "policy_version": policy_version,
        "status": status,
        "old_hash": _digest(old_text),
        "new_hash": _digest(new_text),
        "review_rounds": max(0, review_rounds),
        "error": cleaned_error,
    }
    try:
        memory_dir.mkdir(parents=True, exist_ok=True)
        with (memory_dir / "memory_history.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        return True
    except OSError:
        logger.warning("failed to append memory history", exc_info=True)
        return False


def _digest(text: str) -> str:
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

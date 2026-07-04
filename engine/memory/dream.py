"""Dream — automatic memory consolidation.

Runs periodically after conversations to keep the memory store healthy:
  1. Deduplicate: merge entries with >70% keyword overlap
  2. Prune: archive entries older than 30 days with no recent access
  3. Extract patterns: if 3+ entries share a theme, create a summary
  4. Filter secrets: remove entries that contain API keys / passwords
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interface import MemoryEntry
    from .store import FileMemoryStore


# ---------------------------------------------------------------------------
# Secret patterns — memories matching these are unsafe to keep
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

_PRUNE_DAYS = 30
_OVERLAP_THRESHOLD = 0.70
_PATTERN_MIN_COUNT = 3


def _contains_secret(text: str) -> bool:
    return any(p.search(text) for p in _SECRET_PATTERNS)


def _keywords(text: str) -> set[str]:
    """Extract lowercase keywords (3+ chars) from text."""
    return {w for w in re.findall(r"[a-zA-Z一-鿿]{3,}", text.lower())}


def _keyword_overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = a & b
    smaller = min(len(a), len(b))
    return len(intersection) / smaller


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        # Handle both aware and naive ISO strings
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class DreamReport:
    secrets_removed: int = 0
    merged: int = 0
    pruned: int = 0
    patterns_found: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Preview plan (returned by preview(), consumed by apply())
# ---------------------------------------------------------------------------

@dataclass
class _MergePlan:
    keep_id: str
    remove_ids: list[str]
    merged_content: str

@dataclass
class _DreamPlan:
    secret_ids: list[str]
    prune_ids: list[str]
    merges: list[_MergePlan]
    pattern_summaries: list[str]


# ---------------------------------------------------------------------------
# Consolidator
# ---------------------------------------------------------------------------

class DreamConsolidator:
    """Analyze and consolidate memory entries."""

    def __init__(self, store: FileMemoryStore) -> None:
        self._store = store

    async def preview(self) -> _DreamPlan:
        """Analyze current memories and generate a consolidation plan."""
        entries = await self._store.list_all()
        now = datetime.now(timezone.utc)

        # 1. Secrets
        secret_ids = [e.id for e in entries if _contains_secret(e.content)]

        # 2. Pruning — old + never re-accessed
        prune_ids: list[str] = []
        cutoff = now - timedelta(days=_PRUNE_DAYS)
        for e in entries:
            if e.id in secret_ids:
                continue
            accessed = _parse_iso(e.last_accessed) or _parse_iso(e.created_at)
            if accessed and accessed < cutoff:
                prune_ids.append(e.id)

        # Filter out pruned/secret entries for dedup + pattern analysis
        active_ids = {e.id for e in entries} - set(secret_ids) - set(prune_ids)
        active = [e for e in entries if e.id in active_ids]

        # 3. Deduplication
        kw_cache: dict[str, set[str]] = {e.id: _keywords(e.content) for e in active}
        merged_away: set[str] = set()
        merges: list[_MergePlan] = []

        for i, a in enumerate(active):
            if a.id in merged_away:
                continue
            group = [a]
            for b in active[i + 1 :]:
                if b.id in merged_away:
                    continue
                if _keyword_overlap(kw_cache[a.id], kw_cache[b.id]) >= _OVERLAP_THRESHOLD:
                    group.append(b)
                    merged_away.add(b.id)
            if len(group) > 1:
                # Keep the newest; merge contents
                group.sort(key=lambda e: e.created_at, reverse=True)
                keep = group[0]
                remove_ids = [e.id for e in group[1:]]
                combined = keep.content
                for e in group[1:]:
                    # Append unique lines from older entries
                    for line in e.content.splitlines():
                        if line.strip() and line not in combined:
                            combined += "\n" + line
                merges.append(_MergePlan(
                    keep_id=keep.id,
                    remove_ids=remove_ids,
                    merged_content=combined,
                ))

        # 4. Pattern extraction — cluster by shared keywords
        remaining = [e for e in active if e.id not in merged_away]
        pattern_summaries: list[str] = []
        used_in_pattern: set[str] = set()

        for i, anchor in enumerate(remaining):
            if anchor.id in used_in_pattern:
                continue
            cluster = [anchor]
            for other in remaining[i + 1 :]:
                if other.id in used_in_pattern:
                    continue
                if _keyword_overlap(kw_cache[anchor.id], kw_cache.get(other.id, set())) >= 0.5:
                    cluster.append(other)
            if len(cluster) >= _PATTERN_MIN_COUNT:
                for e in cluster:
                    used_in_pattern.add(e.id)
                # Build a theme summary from shared keywords
                shared = kw_cache[cluster[0].id]
                for e in cluster[1:]:
                    shared = shared & kw_cache.get(e.id, set())
                theme = ", ".join(sorted(shared)[:8]) if shared else "related topics"
                summary = f"Pattern ({len(cluster)} entries): {theme}"
                pattern_summaries.append(summary)

        return _DreamPlan(
            secret_ids=secret_ids,
            prune_ids=prune_ids,
            merges=merges,
            pattern_summaries=pattern_summaries,
        )

    async def apply(self) -> DreamReport:
        """Execute consolidation: secrets, prune, merge, patterns."""
        plan = await self.preview()
        report = DreamReport()

        # Remove secrets
        for eid in plan.secret_ids:
            try:
                await self._store.remove(eid)
                report.secrets_removed += 1
            except Exception as exc:
                report.errors.append(f"secret remove {eid}: {exc}")

        # Prune old entries
        for eid in plan.prune_ids:
            try:
                await self._store.remove(eid)
                report.pruned += 1
            except Exception as exc:
                report.errors.append(f"prune {eid}: {exc}")

        # Merge duplicates
        for merge in plan.merges:
            try:
                await self._store.update(merge.keep_id, content=merge.merged_content)
                for eid in merge.remove_ids:
                    await self._store.remove(eid)
                report.merged += len(merge.remove_ids)
            except Exception as exc:
                report.errors.append(f"merge {merge.keep_id}: {exc}")

        # Create pattern summaries
        for summary in plan.pattern_summaries:
            try:
                await self._store.add(
                    content=summary,
                    evidence="dream consolidation",
                    scope="agent",
                )
                report.patterns_found += 1
            except Exception as exc:
                report.errors.append(f"pattern: {exc}")

        return report

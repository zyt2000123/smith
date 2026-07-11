"""Memory search — FTS5 full-text index with trigram tokenizer.

Per-agent search index under the agent profile's memory dir (…/<id>/memory/search.sqlite).
Uses trigram tokenizer for CJK (Chinese/Japanese/Korean) support.

Usage:
    idx = SearchIndex(memory_dir)
    await idx.open()
    await idx.index_entry(id, content, scope)
    results = await idx.search("query", top_k=10)
    await idx.close()
"""

from __future__ import annotations

import aiosqlite
from pathlib import Path

_SCHEMA_VERSION = "2"


class SearchIndex:
    def __init__(self, memory_dir: Path) -> None:
        self._db_path = memory_dir / "search.sqlite"
        self._version_path = memory_dir / ".fts_version"
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        needs_rebuild = self._needs_rebuild()
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=3000")
        if needs_rebuild:
            await self._db.execute("DROP TABLE IF EXISTS memory_fts")
        await self._db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(entry_id, content, scope, tokenize='trigram')
        """)
        await self._db.commit()
        if needs_rebuild:
            self._version_path.write_text(_SCHEMA_VERSION, encoding="utf-8")
            mtime_marker = self._db_path.parent / ".index_mtime"
            if mtime_marker.exists():
                mtime_marker.unlink()

    def _needs_rebuild(self) -> bool:
        if not self._db_path.exists():
            return True
        if not self._version_path.exists():
            return True
        try:
            return self._version_path.read_text(encoding="utf-8").strip() != _SCHEMA_VERSION
        except OSError:
            return True

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def index_entry(self, entry_id: str, content: str, scope: str) -> None:
        if not self._db:
            return
        await self._db.execute("DELETE FROM memory_fts WHERE entry_id = ?", (entry_id,))
        await self._db.execute(
            "INSERT INTO memory_fts (entry_id, content, scope) VALUES (?, ?, ?)",
            (entry_id, content, scope),
        )
        await self._db.commit()

    async def remove_entry(self, entry_id: str) -> None:
        if not self._db:
            return
        await self._db.execute("DELETE FROM memory_fts WHERE entry_id = ?", (entry_id,))
        await self._db.commit()

    async def search(self, query: str, top_k: int = 10) -> list[dict]:
        if not self._db:
            return []
        rows = await self._db.execute_fetchall(
            "SELECT entry_id, bm25(memory_fts) AS score "
            "FROM memory_fts WHERE memory_fts MATCH ? "
            "ORDER BY score LIMIT ?",
            (query, top_k),
        )
        return [{"id": r["entry_id"], "score": -r["score"]} for r in rows]

"""Memory search — FTS5 full-text index.

Per-agent search index under the agent profile's memory dir (…/<id>/memory/search.sqlite).

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


class SearchIndex:
    def __init__(self, memory_dir: Path) -> None:
        self._db_path = memory_dir / "search.sqlite"
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(entry_id, content, scope, tokenize='unicode61')
        """)
        await self._db.commit()

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

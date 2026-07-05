"""Hybrid memory search — FTS5 full-text + sqlite-vec semantic + RRF fusion.

Per-employee search index at ~/.agent-smith/employees/<id>/memory/search.sqlite.
FTS5 is always available (built into SQLite). sqlite-vec is optional (graceful fallback).

Usage:
    idx = SearchIndex(memory_dir)
    await idx.open(embedding_fn)        # embedding_fn is optional
    await idx.index_entry(id, content, scope)
    results = await idx.search("query", top_k=10)
    await idx.close()
"""

from __future__ import annotations

import struct
from typing import Callable, Awaitable

import aiosqlite
from pathlib import Path


def _serialize_f32(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


class SearchIndex:
    def __init__(self, memory_dir: Path) -> None:
        self._db_path = memory_dir / "search.sqlite"
        self._db: aiosqlite.Connection | None = None
        self._has_vec = False
        self._embed_fn: Callable[[str], Awaitable[list[float]]] | None = None
        self._dim = 0

    async def open(
        self,
        embed_fn: Callable[[str], Awaitable[list[float]]] | None = None,
        dim: int = 1024,
    ) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")

        # FTS5 (always available)
        await self._db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(entry_id, content, scope, tokenize='unicode61')
        """)

        # sqlite-vec (optional)
        self._embed_fn = embed_fn
        self._dim = dim
        if embed_fn:
            try:
                import sqlite_vec
                raw = self._db._connection
                raw.enable_load_extension(True)
                sqlite_vec.load(raw)
                raw.enable_load_extension(False)
                await self._db.execute(f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec
                    USING vec0(entry_id TEXT PRIMARY KEY, embedding float[{dim}])
                """)
                self._has_vec = True
            except (ImportError, Exception):
                self._has_vec = False

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

        if self._has_vec and self._embed_fn:
            try:
                vec = await self._embed_fn(content[:2000])
                await self._db.execute("DELETE FROM memory_vec WHERE entry_id = ?", (entry_id,))
                await self._db.execute(
                    "INSERT INTO memory_vec (entry_id, embedding) VALUES (?, ?)",
                    (entry_id, _serialize_f32(vec)),
                )
            except Exception:
                pass

        await self._db.commit()

    async def remove_entry(self, entry_id: str) -> None:
        if not self._db:
            return
        await self._db.execute("DELETE FROM memory_fts WHERE entry_id = ?", (entry_id,))
        if self._has_vec:
            try:
                await self._db.execute("DELETE FROM memory_vec WHERE entry_id = ?", (entry_id,))
            except Exception:
                pass
        await self._db.commit()

    async def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Hybrid search: FTS5 + vector, fused with RRF."""
        if not self._db:
            return []

        fts_results = await self._fts_search(query, top_k * 2)

        vec_results: list[tuple[str, float]] = []
        if self._has_vec and self._embed_fn:
            try:
                vec_results = await self._vec_search(query, top_k * 2)
            except Exception:
                pass

        if not vec_results:
            return [{"id": eid, "score": score} for eid, score in fts_results[:top_k]]

        return self._rrf_fuse(fts_results, vec_results, top_k)

    async def _fts_search(self, query: str, limit: int) -> list[tuple[str, float]]:
        rows = await self._db.execute_fetchall(
            "SELECT entry_id, bm25(memory_fts) AS score "
            "FROM memory_fts WHERE memory_fts MATCH ? "
            "ORDER BY score LIMIT ?",
            (query, limit),
        )
        return [(r["entry_id"], -r["score"]) for r in rows]

    async def _vec_search(self, query: str, limit: int) -> list[tuple[str, float]]:
        query_vec = await self._embed_fn(query[:2000])
        rows = await self._db.execute_fetchall(
            "SELECT entry_id, distance FROM memory_vec "
            "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (_serialize_f32(query_vec), limit),
        )
        return [(r["entry_id"], 1.0 / (1.0 + r["distance"])) for r in rows]

    @staticmethod
    def _rrf_fuse(
        fts: list[tuple[str, float]],
        vec: list[tuple[str, float]],
        top_k: int,
        k: int = 60,
    ) -> list[dict]:
        """Reciprocal Rank Fusion."""
        scores: dict[str, float] = {}
        for rank, (eid, _) in enumerate(fts):
            scores[eid] = scores.get(eid, 0) + 1.0 / (k + rank + 1)
        for rank, (eid, _) in enumerate(vec):
            scores[eid] = scores.get(eid, 0) + 1.0 / (k + rank + 1)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [{"id": eid, "score": score} for eid, score in ranked[:top_k]]


async def create_jina_embed_fn(
    api_key: str,
    base_url: str,
    model: str = "jina-embeddings-v3",
) -> Callable[[str], Awaitable[list[float]]]:
    """Create an embedding function using Jina via OpenAI-compatible API."""
    import httpx

    client = httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=httpx.Timeout(30.0, connect=10.0),
    )

    async def embed(text: str) -> list[float]:
        resp = await client.post("/embeddings", json={
            "model": model,
            "input": [text],
            "encoding_format": "float",
        })
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]

    embed._client = client  # type: ignore[attr-defined]
    return embed

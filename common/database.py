from __future__ import annotations

import asyncio

import aiosqlite

from .config import SQLITE_PATH, ensure_dirs

_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is not None:
        return _db

    async with _db_lock:
        if _db is not None:
            return _db
        ensure_dirs()
        db = await aiosqlite.connect(str(SQLITE_PATH))
        try:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            # Wait for a concurrent writer (server/CLI share this file) instead
            # of failing immediately with "database is locked".
            await db.execute("PRAGMA busy_timeout=5000")
        except BaseException:
            await db.close()
            raise
        _db = db
        return db


async def close_db() -> None:
    global _db
    async with _db_lock:
        if _db is None:
            return
        db = _db
        _db = None
        await db.close()

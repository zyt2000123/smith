from __future__ import annotations

import aiosqlite

from .config import SQLITE_PATH, ensure_dirs

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        ensure_dirs()
        _db = await aiosqlite.connect(str(SQLITE_PATH))
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None

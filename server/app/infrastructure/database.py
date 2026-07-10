from __future__ import annotations

import aiosqlite

from common.database import get_db

from .schema import ensure_schema

_initialized_db: aiosqlite.Connection | None = None


async def get_app_db() -> aiosqlite.Connection:
    global _initialized_db
    db = await get_db()
    if _initialized_db is not db:
        await ensure_schema(db)
        _initialized_db = db
    return db

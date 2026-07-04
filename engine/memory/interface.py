from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass
class MemoryEntry:
    id: str
    content: str
    scope: Literal["agent", "project"]
    evidence: str
    created_at: str
    last_accessed: str = ""


class MemoryStore(Protocol):
    async def search(self, query: str) -> list[MemoryEntry]: ...
    async def add(self, content: str, evidence: str, scope: str) -> MemoryEntry: ...
    async def update(self, entry_id: str, content: str | None = None, evidence: str | None = None) -> bool: ...
    async def remove(self, entry_id: str) -> bool: ...

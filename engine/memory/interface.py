from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class MemoryEntry:
    id: str
    content: str
    scope: Literal["agent", "project"]
    evidence: str
    created_at: str


class MemoryStore(Protocol):
    async def search(self, query: str) -> list[MemoryEntry]: ...
    async def add(self, content: str, evidence: str, scope: str) -> MemoryEntry: ...
    async def remove(self, entry_id: str) -> bool: ...

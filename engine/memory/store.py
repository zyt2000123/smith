from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from .interface import MemoryEntry


class FileMemoryStore:
    """File-based memory store reading from an employee's memory/ directory.

    Each memory entry is a plain-text file: <id>.md with YAML-like header.
    Search is simple keyword matching.
    """

    def __init__(self, memory_dir: Path) -> None:
        self._dir = memory_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    async def search(self, query: str) -> list[MemoryEntry]:
        results: list[MemoryEntry] = []
        keywords = query.lower().split()
        if not keywords:
            return results

        for f in sorted(self._dir.glob("*.md")):
            content = f.read_text(encoding="utf-8")
            lower_content = content.lower()
            if any(kw in lower_content for kw in keywords):
                entry = self._parse_file(f, content)
                if entry:
                    results.append(entry)

        return results

    async def add(self, content: str, evidence: str, scope: str) -> MemoryEntry:
        entry_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        entry = MemoryEntry(
            id=entry_id,
            content=content,
            scope=scope,  # type: ignore[arg-type]
            evidence=evidence,
            created_at=now,
        )

        text = (
            f"---\n"
            f"id: {entry.id}\n"
            f"scope: {entry.scope}\n"
            f"created_at: {entry.created_at}\n"
            f"---\n"
            f"{entry.content}\n\n"
            f"Evidence: {entry.evidence}\n"
        )
        (self._dir / f"{entry.id}.md").write_text(text, encoding="utf-8")
        return entry

    async def remove(self, entry_id: str) -> bool:
        path = self._dir / f"{entry_id}.md"
        if path.is_file():
            path.unlink()
            return True
        return False

    @staticmethod
    def _parse_file(path: Path, raw: str) -> MemoryEntry | None:
        """Parse a memory file with YAML frontmatter."""
        entry_id = path.stem
        scope = "agent"
        created_at = ""
        body = raw

        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().splitlines():
                    if line.startswith("scope:"):
                        scope = line.split(":", 1)[1].strip()
                    elif line.startswith("created_at:"):
                        created_at = line.split(":", 1)[1].strip()
                    elif line.startswith("id:"):
                        entry_id = line.split(":", 1)[1].strip()
                body = parts[2].strip()

        # Split body from evidence
        evidence = ""
        if "\nEvidence:" in body:
            body_part, evidence = body.rsplit("\nEvidence:", 1)
            body = body_part.strip()
            evidence = evidence.strip()

        return MemoryEntry(
            id=entry_id,
            content=body,
            scope=scope,  # type: ignore[arg-type]
            evidence=evidence,
            created_at=created_at,
        )


async def save_conversation_memory(
    employee_dir: Path, user_msg: str, reply: str, had_tools: bool
) -> None:
    """Save a memory entry after a conversation that involved tool usage."""
    if not had_tools:
        return  # Simple Q&A doesn't need memory

    import json

    memory_dir = employee_dir / "memory" / "conversations"
    memory_dir.mkdir(parents=True, exist_ok=True)

    recent_file = employee_dir / "memory" / "recent.jsonl"
    recent_file.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "task": user_msg[:100],
        "summary": reply[:200],
        "timestamp": now,
    }

    # Append to recent.jsonl
    with open(recent_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Also save as a memory entry via the store
    store = FileMemoryStore(employee_dir / "memory")
    await store.add(
        content=f"Task: {user_msg[:100]}\nResult: {reply[:200]}",
        evidence=f"conversation at {now}",
        scope="agent",
    )

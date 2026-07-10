from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from engine.llm.client import ChatResponse
from engine.memory.compile import (
    MAX_DURABLE_CHARS,
    compact_episode,
    compile_durable,
    compile_recent,
    run_compilation,
)
from engine.memory.dream import run_dream
from engine.memory.store import FileMemoryStore, save_conversation_memory


class StaticLLM:
    def __init__(self, text: str = "summary") -> None:
        self.text = text
        self.calls: list[list[dict]] = []

    async def chat(self, messages: list[dict], **_: object) -> ChatResponse:
        self.calls.append(messages)
        return ChatResponse(text=self.text)


def test_compact_episode_keeps_untrusted_topics_inside_episodes(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    memory_dir = profile_dir / "memory"
    profile_dir.mkdir()
    role_path = profile_dir / "role.md"
    role_path.write_text("original identity", encoding="utf-8")

    async def run() -> list[Path | None]:
        llm = StaticLLM()
        return [
            await compact_episode(memory_dir, llm, "../../role", [{"task": "a"}]),
            await compact_episode(memory_dir, llm, "/tmp/escape", [{"task": "b"}]),
            await compact_episode(memory_dir, llm, "///", [{"task": "c"}]),
        ]

    escaped_role, escaped_absolute, empty_topic = asyncio.run(run())
    episodes_dir = (memory_dir / "episodes").resolve()

    assert escaped_role is not None
    assert escaped_role.resolve().is_relative_to(episodes_dir)
    assert escaped_absolute is not None
    assert escaped_absolute.resolve().is_relative_to(episodes_dir)
    assert empty_topic is None
    assert role_path.read_text(encoding="utf-8") == "original identity"


def test_file_memory_store_rejects_traversal_ids(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    memory_dir = profile_dir / "memory"
    (memory_dir / "agent").mkdir(parents=True)
    role_path = profile_dir / "role.md"
    role_path.write_text("original identity", encoding="utf-8")
    store = FileMemoryStore(memory_dir)

    async def run() -> tuple[bool, bool, bool, bool]:
        return (
            await store.update("../../role", content="attacker", evidence="attacker"),
            await store.remove("../../role"),
            await store.update("/tmp/role", content="attacker", evidence="attacker"),
            await store.remove("/tmp/role"),
        )

    assert asyncio.run(run()) == (False, False, False, False)
    assert role_path.read_text(encoding="utf-8") == "original identity"


def test_save_conversation_memory_skips_toolless_turns_and_only_appends_events(tmp_path: Path) -> None:
    async def run() -> None:
        await save_conversation_memory(tmp_path, "plain chat", "plain reply", had_tools=False)
        assert not (tmp_path / "memory").exists()

        await save_conversation_memory(tmp_path, "used a tool", "completed task", had_tools=True)

    asyncio.run(run())

    memory_dir = tmp_path / "memory"
    entries = [json.loads(line) for line in (memory_dir / "recent.jsonl").read_text(encoding="utf-8").splitlines()]
    assert entries[0]["task"] == "used a tool"
    assert not list(memory_dir.glob("*.md"))


def test_compile_recent_uses_fingerprint_to_skip_unchanged_input(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    event = {
        "task": "implemented safe memory writes",
        "summary": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    (memory_dir / "recent.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

    async def run() -> tuple[bool, bool]:
        llm = StaticLLM()
        return await compile_recent(memory_dir, llm), await compile_recent(memory_dir, llm)

    assert asyncio.run(run()) == (True, False)
    assert "implemented safe memory writes" in (memory_dir / "recent.md").read_text(encoding="utf-8")


def test_compile_durable_enforces_its_character_budget(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    event = {
        "task": "durable-memory task",
        "summary": "durable-memory result",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    (memory_dir / "recent.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    llm = StaticLLM("x" * (MAX_DURABLE_CHARS * 2))

    assert asyncio.run(compile_durable(memory_dir, llm)) is True

    durable = (memory_dir / "durable.md").read_text(encoding="utf-8")
    assert len(durable) <= MAX_DURABLE_CHARS
    assert f"within {MAX_DURABLE_CHARS} characters" in llm.calls[0][1]["content"]


def test_run_compilation_keeps_durable_working_when_recent_fails(tmp_path: Path) -> None:
    async def run() -> dict:
        with (
            patch(
                "engine.memory.compile.compile_recent",
                new=AsyncMock(side_effect=RuntimeError("recent failed")),
            ),
            patch(
                "engine.memory.compile.compile_durable",
                new=AsyncMock(return_value=True),
            ),
        ):
            return await run_compilation(tmp_path / "memory", StaticLLM())

    assert asyncio.run(run()) == {"recent": False, "durable": True}


def test_dream_keeps_a_backup_before_replacing_durable_memory(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    original = "## Durable Memory\n\n" + ("old fact " * 20)
    (memory_dir / "durable.md").write_text(original, encoding="utf-8")
    replacement = ("new durable fact " * 10).strip()

    report = asyncio.run(run_dream(memory_dir, StaticLLM(replacement)))

    assert report.consolidated is True
    assert (memory_dir / "durable.md.bak").read_text(encoding="utf-8") == original
    assert (memory_dir / "durable.md").read_text(encoding="utf-8") == replacement + "\n"

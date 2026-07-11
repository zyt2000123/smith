from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import ANY, AsyncMock, patch

import pytest

from engine.llm import model_config
from engine.llm.client import ChatResponse
from engine.memory.compile import (
    MAX_DURABLE_CHARS,
    _entries_to_source,
    compact_episode,
    compile_durable,
    compile_recent,
    run_compilation,
)
from engine.memory.dream import DreamReport, run_dream
from engine.memory.store import _MAX_EVENT_VALUE_CHARS, FileMemoryStore, save_conversation_memory


class StaticLLM:
    def __init__(self, text: str = "summary") -> None:
        self.text = text
        self.calls: list[list[dict]] = []

    async def chat(self, messages: list[dict], **_: object) -> ChatResponse:
        self.calls.append(messages)
        return ChatResponse(text=self.text)

    async def close(self) -> None:
        return None


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


def test_save_conversation_memory_preserves_normal_sized_event_content(tmp_path: Path) -> None:
    task = "task-" + ("x" * 150)
    reply = "reply-" + ("y" * 250)

    asyncio.run(save_conversation_memory(tmp_path, task, reply, had_tools=True))

    entry = json.loads((tmp_path / "memory" / "recent.jsonl").read_text(encoding="utf-8"))
    assert entry["task"] == task
    assert entry["summary"] == reply


def test_save_conversation_memory_marks_only_exceptionally_large_values(tmp_path: Path) -> None:
    task = "task-start-" + ("x" * _MAX_EVENT_VALUE_CHARS) + "-task-end"

    asyncio.run(save_conversation_memory(tmp_path, task, "reply", had_tools=True))

    entry = json.loads((tmp_path / "memory" / "recent.jsonl").read_text(encoding="utf-8"))
    assert len(entry["task"]) <= _MAX_EVENT_VALUE_CHARS
    assert entry["task"].startswith("task-start-")
    assert entry["task"].endswith("-task-end")
    assert "[Memory event truncated for storage]" in entry["task"]


def test_entries_to_source_keeps_full_normal_event_summary() -> None:
    summary = "decision-" + ("x" * 160)

    source = _entries_to_source([
        {"timestamp": "2026-07-10T00:00:00+00:00", "task": "memory repair", "summary": summary},
    ])

    assert summary in source


def test_save_conversation_memory_retries_compilation_after_missing_llm_config(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / ".compile_counter").write_text("4", encoding="utf-8")

    async def run() -> None:
        with patch.object(model_config, "resolve_llm_config", return_value={"api_key": ""}):
            await save_conversation_memory(tmp_path, "task", "reply", had_tools=True)
            await save_conversation_memory(tmp_path, "task", "reply", had_tools=True)

    asyncio.run(run())

    assert (memory_dir / ".compile_counter").read_text(encoding="utf-8") == "5"


def test_save_conversation_memory_retries_compilation_after_failure(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / ".compile_counter").write_text("4", encoding="utf-8")

    async def run() -> None:
        with (
            patch.object(
                model_config,
                "resolve_llm_config",
                return_value={"api_key": "test", "base_url": "https://example.invalid", "model": "test"},
            ),
            patch.object(model_config, "build_llm_client", return_value=StaticLLM()),
            patch(
                "engine.memory.compile.run_compilation",
                new=AsyncMock(side_effect=RuntimeError("compilation failed")),
            ),
        ):
            await save_conversation_memory(tmp_path, "task", "reply", had_tools=True)

    asyncio.run(run())

    assert (memory_dir / ".compile_counter").read_text(encoding="utf-8") == "5"


def test_save_conversation_memory_resets_compilation_counter_after_success(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / ".compile_counter").write_text("4", encoding="utf-8")

    async def run() -> tuple[AsyncMock, object]:
        compile = AsyncMock(return_value={"recent": True, "durable": True})
        with (
            patch.object(
                model_config,
                "resolve_llm_config",
                return_value={"api_key": "test", "base_url": "https://example.invalid", "model": "test"},
            ) as resolve,
            patch.object(model_config, "build_llm_client", return_value=StaticLLM()),
            patch("engine.memory.compile.run_compilation", new=compile),
        ):
            await save_conversation_memory(tmp_path, "task", "reply", had_tools=True)
        return compile, resolve

    compile, resolve = asyncio.run(run())

    compile.assert_awaited_once_with(memory_dir, ANY, raise_on_error=True)
    resolve.assert_called_once_with(tmp_path.name, usage=model_config.LLMUsage.BACKGROUND)
    assert (memory_dir / ".compile_counter").read_text(encoding="utf-8") == "0"


def test_save_conversation_memory_compiles_real_memory_layers_after_five_turns(tmp_path: Path) -> None:
    llm = StaticLLM("stable project decision")

    async def run() -> None:
        with (
            patch.object(
                model_config,
                "resolve_llm_config",
                return_value={"api_key": "test", "base_url": "https://example.invalid", "model": "test"},
            ),
            patch.object(model_config, "build_llm_client", return_value=llm),
        ):
            for turn in range(5):
                await save_conversation_memory(tmp_path, f"task {turn}", f"reply {turn}", had_tools=True)

    asyncio.run(run())

    memory_dir = tmp_path / "memory"
    assert (memory_dir / "recent.md").is_file()
    assert (memory_dir / "durable.md").is_file()
    assert (memory_dir / ".compile_counter").read_text(encoding="utf-8") == "0"


def test_save_conversation_memory_retries_dream_after_missing_llm_config(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / ".dream_counter").write_text("49", encoding="utf-8")

    async def run() -> None:
        with patch.object(model_config, "resolve_llm_config", return_value={"api_key": ""}):
            await save_conversation_memory(tmp_path, "task", "reply", had_tools=True)
            await save_conversation_memory(tmp_path, "task", "reply", had_tools=True)

    asyncio.run(run())

    assert (memory_dir / ".dream_counter").read_text(encoding="utf-8") == "50"


def test_save_conversation_memory_retries_dream_after_failure(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / ".dream_counter").write_text("49", encoding="utf-8")

    async def run() -> None:
        with (
            patch.object(
                model_config,
                "resolve_llm_config",
                return_value={"api_key": "test", "base_url": "https://example.invalid", "model": "test"},
            ),
            patch.object(model_config, "build_llm_client", return_value=StaticLLM()),
            patch(
                "engine.memory.dream.run_dream",
                new=AsyncMock(return_value=DreamReport(errors=["consolidation failed"])),
            ),
        ):
            await save_conversation_memory(tmp_path, "task", "reply", had_tools=True)

    asyncio.run(run())

    assert (memory_dir / ".dream_counter").read_text(encoding="utf-8") == "50"


def test_save_conversation_memory_creates_episode_for_explicit_summary_request(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    llm = StaticLLM()
    episode_path = memory_dir / "episodes" / "memory-repair.md"

    async def run() -> AsyncMock:
        compact = AsyncMock(return_value=episode_path)
        with (
            patch.object(
                model_config,
                "resolve_llm_config",
                return_value={"api_key": "test", "base_url": "https://example.invalid", "model": "test"},
            ),
            patch.object(model_config, "build_llm_client", return_value=llm),
            patch("engine.memory.compile.compact_episode", new=compact),
        ):
            await save_conversation_memory(
                tmp_path,
                "请整理一下这段 memory 修复过程",
                "修复完成",
                had_tools=True,
            )
        return compact

    compact = asyncio.run(run())

    compact.assert_awaited_once()
    args = compact.await_args.args
    assert args[0] == memory_dir
    assert "memory 修复过程" in args[2]
    assert len(args[3]) == 1


def test_save_conversation_memory_does_not_create_episode_for_normal_task(tmp_path: Path) -> None:
    compact = AsyncMock()

    async def run() -> None:
        with (
            patch.object(
                model_config,
                "resolve_llm_config",
                return_value={"api_key": "test", "base_url": "https://example.invalid", "model": "test"},
            ),
            patch.object(model_config, "build_llm_client", return_value=StaticLLM()),
            patch("engine.memory.compile.compact_episode", new=compact),
        ):
            await save_conversation_memory(tmp_path, "修复 memory 模块", "修复完成", had_tools=True)

    asyncio.run(run())

    compact.assert_not_awaited()


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


def test_run_compilation_surfaces_failure_when_retry_is_required(tmp_path: Path) -> None:
    async def run() -> None:
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
            await run_compilation(tmp_path / "memory", StaticLLM(), raise_on_error=True)

    with pytest.raises(RuntimeError, match="recent-memory compilation failed"):
        asyncio.run(run())


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

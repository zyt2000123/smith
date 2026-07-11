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
    _generate_and_review,
    _read_offset,
    compact_episode,
    compile_durable,
    compile_recent,
    run_compilation,
)
from engine.memory.dream import DreamReport, run_dream
from engine.memory.store import _MAX_EVENT_VALUE_CHARS, save_conversation_memory


class StaticLLM:
    def __init__(self, text: str = "summary") -> None:
        self.text = text
        self.calls: list[list[dict]] = []

    async def chat(self, messages: list[dict], **_: object) -> ChatResponse:
        self.calls.append(messages)
        return ChatResponse(text=self.text)

    async def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Path traversal: episodes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# save_conversation_memory
# ---------------------------------------------------------------------------

def test_save_conversation_memory_skips_toolless_turns(tmp_path: Path) -> None:
    async def run() -> None:
        await save_conversation_memory(tmp_path, "plain chat", "plain reply", had_tools=False)
        assert not (tmp_path / "memory").exists()

        await save_conversation_memory(tmp_path, "used a tool", "completed task", had_tools=True)

    asyncio.run(run())

    memory_dir = tmp_path / "memory"
    entries = [json.loads(line) for line in (memory_dir / "recent.jsonl").read_text(encoding="utf-8").splitlines()]
    assert entries[0]["task"] == "used a tool"


def test_save_conversation_memory_preserves_normal_sized_content(tmp_path: Path) -> None:
    task = "fix the memory module " + ("detail " * 20)
    reply = "completed the repair " + ("result " * 30)

    asyncio.run(save_conversation_memory(tmp_path, task, reply, had_tools=True))

    entry = json.loads((tmp_path / "memory" / "recent.jsonl").read_text(encoding="utf-8"))
    assert entry["task"] == task
    assert entry["summary"] == reply


def test_save_conversation_memory_truncates_large_values(tmp_path: Path) -> None:
    task = "task-start-" + ("x" * _MAX_EVENT_VALUE_CHARS) + "-task-end"

    asyncio.run(save_conversation_memory(tmp_path, task, "reply", had_tools=True))

    entry = json.loads((tmp_path / "memory" / "recent.jsonl").read_text(encoding="utf-8"))
    assert len(entry["task"]) <= _MAX_EVENT_VALUE_CHARS
    assert entry["task"].startswith("task-start-")
    assert entry["task"].endswith("-task-end")
    assert "[Memory event truncated for storage]" in entry["task"]


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def test_entries_to_source_keeps_full_normal_event_summary() -> None:
    summary = "decision-" + ("x" * 160)

    source = _entries_to_source([
        {"timestamp": "2026-07-10T00:00:00+00:00", "task": "memory repair", "summary": summary},
    ])

    assert summary in source


def test_compile_recent_uses_fingerprint_to_skip_unchanged(tmp_path: Path) -> None:
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


def test_compile_durable_enforces_character_budget(tmp_path: Path) -> None:
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


def test_run_compilation_keeps_durable_when_recent_fails(tmp_path: Path) -> None:
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


def test_run_compilation_surfaces_failure_when_requested(tmp_path: Path) -> None:
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


# ---------------------------------------------------------------------------
# Offset mechanism
# ---------------------------------------------------------------------------

def test_run_compilation_updates_offset_on_success(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    for i in range(3):
        event = {"task": f"task {i}", "summary": f"reply {i}", "timestamp": datetime.now(timezone.utc).isoformat()}
        with open(memory_dir / "recent.jsonl", "a") as f:
            f.write(json.dumps(event) + "\n")

    async def run() -> int:
        llm = StaticLLM()
        await run_compilation(memory_dir, llm)
        return _read_offset(memory_dir)

    assert asyncio.run(run()) == 3


def test_run_compilation_does_not_update_offset_on_failure(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    event = {"task": "task", "summary": "reply", "timestamp": datetime.now(timezone.utc).isoformat()}
    (memory_dir / "recent.jsonl").write_text(json.dumps(event) + "\n")

    async def run() -> int:
        with patch("engine.memory.compile.compile_recent", new=AsyncMock(side_effect=RuntimeError("fail"))):
            await run_compilation(memory_dir, StaticLLM())
        return _read_offset(memory_dir)

    assert asyncio.run(run()) == 0


# ---------------------------------------------------------------------------
# Generator-evaluator pipeline
# ---------------------------------------------------------------------------

def test_generate_and_review_passes_on_first_try() -> None:
    generator = StaticLLM("good summary")
    reviewer = StaticLLM('{"pass": true, "hard_fail": [], "soft_fail": [], "feedback": ""}')

    result = asyncio.run(_generate_and_review(generator, reviewer, "summarize this", "source data"))

    assert result == "good summary"
    assert len(generator.calls) == 1
    assert len(reviewer.calls) == 1


def test_generate_and_review_exhausts_retries_without_unreviewed_draft() -> None:
    """When all rounds fail, the returned draft was still reviewed (no unreviewed escape)."""
    gen_count = 0
    rev_count = 0

    class CountingGenerator:
        async def chat(self, messages, **_):
            nonlocal gen_count
            gen_count += 1
            return ChatResponse(text=f"draft-{gen_count}")
        async def close(self): pass

    class AlwaysFailReviewer:
        async def chat(self, messages, **_):
            nonlocal rev_count
            rev_count += 1
            return ChatResponse(text='{"pass": false, "hard_fail": ["fabrication"], "soft_fail": [], "feedback": "bad"}')
        async def close(self): pass

    result = asyncio.run(_generate_and_review(CountingGenerator(), AlwaysFailReviewer(), "test", "src"))

    assert rev_count == 3
    assert gen_count <= rev_count


def test_generate_and_review_retries_on_hard_fail() -> None:
    call_count = 0

    class RetryReviewer:
        async def chat(self, messages, **_):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ChatResponse(text='{"pass": false, "hard_fail": ["fabrication"], "soft_fail": [], "feedback": "Contains made-up facts"}')
            return ChatResponse(text='{"pass": true, "hard_fail": [], "soft_fail": [], "feedback": ""}')

        async def close(self):
            pass

    generator = StaticLLM("improved summary")

    result = asyncio.run(_generate_and_review(generator, RetryReviewer(), "summarize", "source"))

    assert result == "improved summary"
    assert len(generator.calls) == 2


# ---------------------------------------------------------------------------
# Compilation counter + retry
# ---------------------------------------------------------------------------

def test_save_conversation_memory_retries_compilation_after_missing_config(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / ".compile_counter").write_text("4", encoding="utf-8")

    async def run() -> None:
        with patch.object(model_config, "resolve_llm_config", return_value={"api_key": ""}):
            await save_conversation_memory(tmp_path, "task", "reply", had_tools=True)
            await save_conversation_memory(tmp_path, "task", "reply", had_tools=True)

    asyncio.run(run())

    assert (memory_dir / ".compile_counter").read_text(encoding="utf-8") == "5"


def test_save_conversation_memory_resets_counter_after_success(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / ".compile_counter").write_text("4", encoding="utf-8")

    async def run() -> None:
        compile_mock = AsyncMock(return_value={"recent": True, "durable": True})
        with (
            patch.object(
                model_config,
                "resolve_llm_config",
                return_value={"api_key": "test", "base_url": "https://example.invalid", "model": "test"},
            ),
            patch.object(model_config, "build_llm_client", return_value=StaticLLM()),
            patch("engine.memory.compile.run_compilation", new=compile_mock),
        ):
            await save_conversation_memory(tmp_path, "task", "reply", had_tools=True)

    asyncio.run(run())

    assert (memory_dir / ".compile_counter").read_text(encoding="utf-8") == "0"


def test_save_conversation_memory_compiles_after_five_turns(tmp_path: Path) -> None:
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


# ---------------------------------------------------------------------------
# Dream
# ---------------------------------------------------------------------------

def test_dream_keeps_backup_before_replacing_durable(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    original = "## Durable Memory\n\n" + ("old fact " * 20)
    (memory_dir / "durable.md").write_text(original, encoding="utf-8")
    replacement = ("new durable fact " * 10).strip()

    report = asyncio.run(run_dream(memory_dir, StaticLLM(replacement)))

    assert report.consolidated is True
    assert (memory_dir / "durable.md.bak").read_text(encoding="utf-8") == original
    assert (memory_dir / "durable.md").read_text(encoding="utf-8") == replacement + "\n"


def test_dream_cleans_log_with_offset(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    lines = []
    for i in range(10):
        lines.append(json.dumps({"task": f"task {i}", "summary": f"reply {i}", "timestamp": "2026-07-10"}))
    (memory_dir / "recent.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (memory_dir / ".compile_offset").write_text("7", encoding="utf-8")
    (memory_dir / "recent.md").write_text("exists", encoding="utf-8")
    (memory_dir / "durable.md").write_text("exists", encoding="utf-8")

    report = asyncio.run(run_dream(memory_dir, StaticLLM()))

    assert report.log_lines_cleaned == 7
    remaining = (memory_dir / "recent.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(remaining) == 3
    assert (memory_dir / ".compile_offset").read_text(encoding="utf-8") == "0"


def test_dream_skips_cleanup_without_compiled_files(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "recent.jsonl").write_text('{"task":"t","summary":"s","timestamp":"now"}\n')
    (memory_dir / ".compile_offset").write_text("1", encoding="utf-8")

    report = asyncio.run(run_dream(memory_dir, StaticLLM()))

    assert report.log_lines_cleaned == 0


def test_dream_sanitizes_all_layers(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    episodes_dir = memory_dir / "episodes"
    episodes_dir.mkdir()
    (memory_dir / "durable.md").write_text("safe line\napi_key: sk-secret123456789012345\nmore safe", encoding="utf-8")
    (episodes_dir / "test.md").write_text("clean\npassword: hunter2\nalso clean", encoding="utf-8")

    report = asyncio.run(run_dream(memory_dir, StaticLLM()))

    assert report.secrets_removed >= 2
    assert "sk-secret" not in (memory_dir / "durable.md").read_text(encoding="utf-8")
    assert "hunter2" not in (episodes_dir / "test.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Dream retry
# ---------------------------------------------------------------------------

def test_save_conversation_memory_retries_dream_after_missing_config(tmp_path: Path) -> None:
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

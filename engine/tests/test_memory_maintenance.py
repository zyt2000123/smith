from __future__ import annotations

import asyncio
from pathlib import Path

from engine.execution.memory_maintenance import (
    MemoryLifecycleHooks,
    MemoryMaintenanceService,
)
from engine.execution.agent_loop import run_memory_idle_tick
from engine.execution.runtime import RuntimeServices
from engine.hook import HookManager, HookType
from engine.llm.client import ChatResponse
from engine.skill.registry import SkillRegistry
from engine.tool.registry import ToolRegistry


class StaticLLM:
    def __init__(self, text: str = "stable memory summary") -> None:
        self.text = text
        self.messages: list[list[dict]] = []

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        prefix_cache_key: str | None = None,
    ) -> ChatResponse:
        self.messages.append(messages)
        return ChatResponse(text=self.text)


def test_memory_after_turn_hook_records_and_compiles(tmp_path: Path) -> None:
    async def run() -> tuple[list[bool], StaticLLM]:
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / ".compile_counter").write_text("4", encoding="utf-8")
        llm = StaticLLM()
        hooks = HookManager()
        hooks.register(MemoryLifecycleHooks(MemoryMaintenanceService(llm)))  # type: ignore[arg-type]

        results = await hooks.apply(
            "memory_after_turn_completed",
            HookType.PARALLEL,
            args=(tmp_path, "remember this", "tool-assisted reply", True),
        )
        return results, llm

    results, llm = asyncio.run(run())

    memory_dir = tmp_path / "memory"
    assert results == [True]
    assert (memory_dir / "recent.jsonl").is_file()
    assert (memory_dir / "recent.md").is_file()
    assert (memory_dir / ".compile_counter").read_text(encoding="utf-8") == "0"
    assert llm.messages


def test_memory_idle_hook_uses_same_maintenance_service(tmp_path: Path) -> None:
    async def run() -> list[bool]:
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "durable.md").write_text("small durable note", encoding="utf-8")
        hooks = HookManager()
        hooks.register(MemoryLifecycleHooks(MemoryMaintenanceService(StaticLLM())))  # type: ignore[arg-type]

        return await hooks.apply(
            "memory_idle_tick",
            HookType.PARALLEL,
            args=(memory_dir,),
        )

    results = asyncio.run(run())

    assert results == [True]


def test_runtime_idle_tick_dispatches_memory_hook(tmp_path: Path) -> None:
    async def run() -> tuple[bool, RuntimeServices]:
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "durable.md").write_text("small durable note", encoding="utf-8")
        services = RuntimeServices(
            llm=StaticLLM(),  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            skill_registry=SkillRegistry(),
        )

        ok = await run_memory_idle_tick(memory_dir, services)
        return ok, services

    ok, services = asyncio.run(run())

    assert ok is True
    assert services.hooks is not None

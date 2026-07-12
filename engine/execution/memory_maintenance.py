"""Lifecycle-owned memory maintenance.

The memory package stays storage/compilation focused. This module owns the
runtime-facing policy: when a lifecycle hook fires, run memory maintenance with
the LLM clients already held by RuntimeServices.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from engine.llm.port import LLMPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryMaintenanceService:
    """Execute memory rules with externally owned runtime dependencies."""

    llm: LLMPort
    reviewer: LLMPort | None = None

    _locks: ClassVar[dict[Path, asyncio.Lock]] = {}

    async def record_turn(
        self,
        agent_dir: Path,
        user_message: str,
        reply_text: str,
        had_tools: bool,
    ) -> bool:
        """Persist a completed turn and run threshold-based maintenance."""
        memory_dir = agent_dir / "memory"
        lock = self._lock_for(memory_dir)
        async with lock:
            try:
                from engine.memory.store import save_conversation_memory

                await save_conversation_memory(
                    agent_dir,
                    user_message,
                    reply_text,
                    had_tools,
                    compile_maintenance=self._run_compilation_unlocked,
                    dream_maintenance=self._run_dream_unlocked,
                )
                return True
            except Exception:
                logger.warning("conversation-memory lifecycle hook failed", exc_info=True)
                return False

    async def run_compile(self, memory_dir: Path) -> bool:
        """Compile recent and durable memory for an explicit trigger."""
        async with self._lock_for(memory_dir):
            return await self._run_compilation_unlocked(memory_dir)

    async def run_dream(self, memory_dir: Path) -> bool:
        """Run Dream maintenance for an explicit trigger."""
        async with self._lock_for(memory_dir):
            return await self._run_dream_unlocked(memory_dir)

    async def run_idle_maintenance(self, memory_dir: Path) -> bool:
        """Run maintenance that is safe for idle/scheduled lifecycle ticks."""
        async with self._lock_for(memory_dir):
            compiled = await self._run_compilation_unlocked(memory_dir)
            dreamed = await self._run_dream_unlocked(memory_dir)
            return compiled and dreamed

    async def _run_compilation_unlocked(self, memory_dir: Path) -> bool:
        try:
            from engine.memory.compile import run_compilation

            await run_compilation(
                memory_dir,
                self.llm,
                reviewer=self.reviewer,
                raise_on_error=True,
            )
            return True
        except Exception:
            logger.warning("conversation-memory compilation failed", exc_info=True)
            return False

    async def _run_dream_unlocked(self, memory_dir: Path) -> bool:
        try:
            from engine.memory.dream import dream_report_completed, run_dream

            report = await run_dream(memory_dir, self.llm, reviewer=self.reviewer)
            if not dream_report_completed(report):
                reason = "; ".join(report.errors) if report.errors else report.skipped
                logger.warning("conversation-memory Dream did not complete: %s", reason)
                return False
            return True
        except Exception:
            logger.warning("conversation-memory Dream consolidation failed", exc_info=True)
            return False

    @classmethod
    def _lock_for(cls, memory_dir: Path) -> asyncio.Lock:
        key = memory_dir.resolve()
        lock = cls._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            cls._locks[key] = lock
        return lock


@dataclass(frozen=True)
class MemoryLifecycleHooks:
    """Hook adapter for memory lifecycle events."""

    maintenance: MemoryMaintenanceService

    async def memory_after_turn_completed(
        self,
        agent_dir: Path,
        user_message: str,
        reply_text: str,
        had_tools: bool,
    ) -> bool:
        return await self.maintenance.record_turn(
            agent_dir,
            user_message,
            reply_text,
            had_tools,
        )

    async def memory_idle_tick(self, memory_dir: Path) -> bool:
        return await self.maintenance.run_idle_maintenance(memory_dir)

    async def memory_daily_tick(self, memory_dir: Path) -> bool:
        return await self.maintenance.run_idle_maintenance(memory_dir)

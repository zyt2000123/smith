"""Plugin hook system — 5 execution modes for extensibility.

Hooks let plugins intercept and modify behavior at key points:
- system_prompt: modify prompt before LLM call (SERIES_LAST)
- tool_use: before tool execution (SERIES)
- tool_result: post-process tool output (SERIES_LAST)
- tools: inject additional tools (SERIES_MERGE)
- after_turn: post-process conversation after each turn (SERIES_LAST)
- stop: after loop ends (SERIES)
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class HookType(Enum):
    FIRST = "first"
    SERIES = "series"
    SERIES_MERGE = "series_merge"
    SERIES_LAST = "series_last"
    PARALLEL = "parallel"


class HookManager:
    def __init__(self) -> None:
        self._plugins: list[Any] = []

    def register(self, plugin: Any) -> None:
        self._plugins.append(plugin)
        self._plugins.sort(
            key=lambda p: {"pre": 0, "": 1, "post": 2}.get(
                getattr(p, "enforce", ""), 1
            )
        )

    def _get_handlers(self, hook: str) -> list[Callable]:
        return [
            fn
            for p in self._plugins
            if (fn := getattr(p, hook, None)) is not None and callable(fn)
        ]

    async def apply(
        self,
        hook: str,
        hook_type: HookType = HookType.SERIES,
        *,
        args: tuple = (),
        initial: Any = None,
    ) -> Any:
        handlers = self._get_handlers(hook)
        if not handlers:
            return initial

        if hook_type == HookType.FIRST:
            for fn in handlers:
                try:
                    result = await _call(fn, *args)
                    if result is not None:
                        return result
                except Exception:
                    logger.debug("hook %s.FIRST error", hook, exc_info=True)
            return None

        if hook_type == HookType.SERIES:
            for fn in handlers:
                try:
                    await _call(fn, *args)
                except Exception:
                    logger.debug("hook %s.SERIES error", hook, exc_info=True)
            return None

        if hook_type == HookType.SERIES_LAST:
            result = initial
            for fn in handlers:
                try:
                    result = await _call(fn, result, *args)
                except Exception:
                    logger.debug("hook %s.SERIES_LAST error", hook, exc_info=True)
            return result

        if hook_type == HookType.SERIES_MERGE:
            result = initial if initial is not None else {}
            is_list = isinstance(result, list)
            for fn in handlers:
                try:
                    partial = await _call(fn, *args)
                    if partial is None:
                        continue
                    if is_list:
                        result = result + (partial if isinstance(partial, list) else [partial])
                    elif isinstance(result, dict) and isinstance(partial, dict):
                        merged = dict(result)
                        merged.update(partial)
                        result = merged
                except Exception:
                    logger.debug("hook %s.SERIES_MERGE error", hook, exc_info=True)
            return result

        if hook_type == HookType.PARALLEL:
            results = await asyncio.gather(
                *[_call(fn, *args) for fn in handlers],
                return_exceptions=True,
            )
            return [r for r in results if r is not None and not isinstance(r, Exception)]

        return initial


async def _call(fn: Callable, *args: Any) -> Any:
    if asyncio.iscoroutinefunction(fn):
        return await fn(*args)
    return fn(*args)


# ── Built-in plugins ─────────────────────────────────────────

class TruncationPlugin:
    name = "truncation"
    enforce = "post"

    def tool_result(self, content: str, tool_name: str = "") -> str:
        from tool.truncation import truncate_output
        return truncate_output(content, tool_name)


class SnapshotPlugin:
    name = "snapshot"
    enforce = "pre"

    def tool_use(self, tool_name: str, params: dict) -> None:
        if tool_name != "write_file":
            return
        path = params.get("path", "")
        if not path or params.get("append", False):
            return
        try:
            from snapshot import get_snapshot
            get_snapshot().track(path)
        except Exception:
            pass


class CompressionPlugin:
    name = "compression"
    enforce = "post"

    def after_turn(self, conversation: list[dict]) -> list[dict]:
        from execution.compression import prune_tool_outputs
        prune_tool_outputs(conversation)
        return conversation


def create_default_hooks() -> HookManager:
    hooks = HookManager()
    hooks.register(TruncationPlugin())
    hooks.register(SnapshotPlugin())
    hooks.register(CompressionPlugin())
    return hooks

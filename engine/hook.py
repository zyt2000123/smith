"""Hook system — 5 execution modes for extensibility.

Hooks let registered handlers intercept and modify behavior at key points:
- system_prompt: modify prompt before LLM call (SERIES_LAST)
- tool_use: before tool execution (SERIES)
- tool_result: post-process tool output (SERIES_LAST)
- tools: inject additional tools (SERIES_MERGE)
- after_turn: post-process conversation after each turn (SERIES_LAST)
- stop: after loop ends (SERIES)
"""

from __future__ import annotations

import asyncio
import inspect
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
        self._handlers: list[Any] = []

    def register(self, handler: Any) -> None:
        self._handlers.append(handler)
        self._handlers.sort(
            key=lambda h: {"pre": 0, "": 1, "post": 2}.get(
                getattr(h, "enforce", ""), 1
            )
        )

    def _get_handlers(self, hook: str) -> list[Callable]:
        return [
            fn
            for h in self._handlers
            if (fn := getattr(h, hook, None)) is not None and callable(fn)
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
            collected: list[Any] = []
            for r in results:
                if isinstance(r, BaseException):
                    logger.debug("hook %s.PARALLEL error", hook, exc_info=r)
                elif r is not None:
                    collected.append(r)
            return collected

        return initial


async def _call(fn: Callable, *args: Any) -> Any:
    # Await by result, not by introspection: iscoroutinefunction misses
    # async callables such as objects with an async __call__, which would
    # silently return an un-awaited coroutine.
    result = fn(*args)
    if inspect.isawaitable(result):
        return await result
    return result

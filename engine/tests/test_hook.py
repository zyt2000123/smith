from __future__ import annotations

import asyncio

from engine.hook import HookManager, HookType


class AsyncCallableHandler:
    """Handler whose hook is an object with an async __call__ (not a
    coroutine function) — regression for un-awaited coroutine drops."""

    def __init__(self) -> None:
        class _Hook:
            called = False

            async def __call__(self, value):
                _Hook.called = True
                return value + "-modified"

        self.system_prompt = _Hook()


def test_series_last_awaits_async_callable_objects():
    manager = HookManager()
    handler = AsyncCallableHandler()
    manager.register(handler)

    result = asyncio.run(
        manager.apply("system_prompt", HookType.SERIES_LAST, initial="base")
    )

    assert result == "base-modified"
    assert handler.system_prompt.called


def test_parallel_collects_results_and_drops_failures():
    class Good:
        async def tools(self):
            return {"name": "good"}

    class Bad:
        async def tools(self):
            raise RuntimeError("boom")

    manager = HookManager()
    manager.register(Good())
    manager.register(Bad())

    result = asyncio.run(manager.apply("tools", HookType.PARALLEL))

    assert result == [{"name": "good"}]

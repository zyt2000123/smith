from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable

from .registry import PluginManifest

log = logging.getLogger(__name__)


class TriggerBase:
    """Base class for plugin triggers."""

    def __init__(self, plugin: PluginManifest) -> None:
        self.plugin = plugin

    async def start(self) -> None:
        """Start the trigger. Override in subclasses."""

    async def stop(self) -> None:
        """Stop the trigger. Override in subclasses."""

    async def poll(self) -> list[dict]:
        """For polling triggers: return list of new events."""
        return []


class PollingTrigger(TriggerBase):
    """Polls an external source at intervals."""

    def __init__(
        self,
        plugin: PluginManifest,
        handler: Callable[[dict], Awaitable[None]],
    ) -> None:
        super().__init__(plugin)
        self._interval = plugin.polling_interval_seconds or 60
        self._handler = handler
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())
        log.info(
            "Polling trigger started for %s (every %ds)",
            self.plugin.name,
            self._interval,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        log.info("Polling trigger stopped for %s", self.plugin.name)

    async def _loop(self) -> None:
        while True:
            try:
                events = await self.poll()
                for event in events:
                    try:
                        await self._handler(event)
                    except Exception:
                        log.exception(
                            "Handler error for plugin %s", self.plugin.name
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Poll error for plugin %s", self.plugin.name)
            await asyncio.sleep(self._interval)


class WebhookTrigger(TriggerBase):
    """Receives webhook POST requests.

    Does not run a background loop. Events are pushed via handle_event()
    from the HTTP router.
    """

    def __init__(
        self,
        plugin: PluginManifest,
        handler: Callable[[dict], Awaitable[None]],
    ) -> None:
        super().__init__(plugin)
        self._handler = handler

    async def handle_event(self, payload: dict) -> dict:
        """Process a single webhook event. Returns a status dict."""
        try:
            await self._handler(payload)
            return {"status": "accepted", "plugin": self.plugin.name}
        except Exception as exc:
            log.exception("Webhook handler error for %s", self.plugin.name)
            return {
                "status": "error",
                "plugin": self.plugin.name,
                "error": str(exc),
            }

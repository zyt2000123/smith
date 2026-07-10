"""Plugin manager service — orchestrates plugin lifecycle."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException

from engine.plugin.registry import PluginRegistry, PluginManifest
from engine.plugin.loader import load_handler
from engine.plugin.trigger import PollingTrigger, WebhookTrigger, CronTrigger, TriggerBase

log = logging.getLogger(__name__)


class PluginService:

    def __init__(self, plugins_dir: Path) -> None:
        self._registry = PluginRegistry(plugins_dir)
        self._triggers: dict[str, TriggerBase] = {}
        self._enabled: set[str] = set()

    # ── Lifecycle ──

    async def startup(self) -> None:
        """Discover plugins and start enabled polling triggers."""
        manifests = self._registry.discover()
        for m in manifests:
            self._enabled.add(m.name)
            await self._init_trigger(m)
        log.info("Plugin service started: %d plugin(s)", len(manifests))

    async def shutdown(self) -> None:
        """Stop all running triggers."""
        for trigger in self._triggers.values():
            await trigger.stop()
        self._triggers.clear()
        log.info("Plugin service stopped")

    # ── API ──

    def list_plugins(self) -> list[dict]:
        plugins = self._registry.list_all()
        for p in plugins:
            enabled = p["name"] in self._enabled
            p["enabled"] = enabled
            p["installed"] = True
            p["status"] = "enabled" if enabled else "disabled"
            p["skill_count"] = len(p.get("skills", []))
        return plugins

    def get_plugin(self, name: str) -> PluginManifest | None:
        return self._registry.get(name)

    async def receive_webhook(
        self,
        name: str,
        payload: dict,
        *,
        github_event: str | None = None,
    ) -> dict:
        if self.get_plugin(name) is None:
            raise HTTPException(404, f"Plugin '{name}' not found")

        event_payload = dict(payload)
        if github_event:
            event_payload["_github_event"] = github_event

        result = await self.handle_webhook(name, event_payload)
        if result.get("status") == "error":
            raise HTTPException(400, result.get("error", "handler error"))
        return result

    async def enable_plugin_or_404(self, name: str) -> dict:
        if not await self.enable_plugin(name):
            raise HTTPException(404, f"Plugin '{name}' not found")
        return {"status": "enabled", "plugin": name}

    async def disable_plugin_or_404(self, name: str) -> dict:
        if not await self.disable_plugin(name):
            raise HTTPException(404, f"Plugin '{name}' not found")
        return {"status": "disabled", "plugin": name}

    async def enable_plugin(self, name: str) -> bool:
        manifest = self._registry.get(name)
        if manifest is None:
            return False
        if name not in self._enabled:
            self._enabled.add(name)
            await self._init_trigger(manifest)
        return True

    async def disable_plugin(self, name: str) -> bool:
        manifest = self._registry.get(name)
        if manifest is None:
            return False
        self._enabled.discard(name)
        trigger = self._triggers.pop(name, None)
        if trigger is not None:
            await trigger.stop()
        return True

    async def handle_webhook(self, name: str, payload: dict) -> dict:
        """Route a webhook event to the right plugin."""
        if name not in self._enabled:
            return {"status": "error", "error": f"Plugin '{name}' is not enabled"}

        trigger = self._triggers.get(name)
        if not isinstance(trigger, WebhookTrigger):
            return {"status": "error", "error": f"Plugin '{name}' is not a webhook plugin"}

        result = await trigger.handle_event(payload)

        # If the handler produced a task dict, log it.
        # A real integration would create an auto-task or session here.
        task = payload.get("_task")
        if task:
            log.info(
                "Plugin '%s' produced task: %s",
                name,
                task.get("title", "(untitled)"),
            )

        return result

    # ── Internal ──

    async def _init_trigger(self, manifest: PluginManifest) -> None:
        handler = load_handler(manifest)
        if handler is None:
            return

        if manifest.trigger_type == "polling":
            trigger = PollingTrigger(manifest, handler)
            self._triggers[manifest.name] = trigger
            await trigger.start()
        elif manifest.trigger_type == "cron":
            cron_expr = manifest.to_dict().get("cron_expression", "0 18 * * *")
            trigger = CronTrigger(manifest, handler, cron_expr)
            self._triggers[manifest.name] = trigger
            await trigger.start()
        elif manifest.trigger_type == "webhook":
            trigger = WebhookTrigger(manifest, handler)
            self._triggers[manifest.name] = trigger
            # Webhook triggers don't start a loop — they wait for HTTP calls

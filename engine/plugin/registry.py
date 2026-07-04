from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)


@dataclass
class PluginManifest:
    """Schema for plugin.json manifests."""

    schema: str = "agentsmith.plugin.v1"
    name: str = ""
    version: str = "0.1.0"
    description: str = ""
    trigger_type: Literal["polling", "webhook", "manual"] = "manual"
    polling_interval_seconds: int | None = None
    skills: list[dict] = field(default_factory=list)
    # Resolved at load time, not serialized
    plugin_dir: Path = field(default_factory=lambda: Path("."), repr=False)

    @classmethod
    def from_dict(cls, data: dict, plugin_dir: Path) -> PluginManifest:
        return cls(
            schema=data.get("schema", "agentsmith.plugin.v1"),
            name=data.get("name", plugin_dir.name),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            trigger_type=data.get("trigger_type", "manual"),
            polling_interval_seconds=data.get("polling_interval_seconds"),
            skills=data.get("skills", []),
            plugin_dir=plugin_dir,
        )

    def to_dict(self) -> dict:
        result: dict = {
            "schema": self.schema,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "trigger_type": self.trigger_type,
        }
        if self.polling_interval_seconds is not None:
            result["polling_interval_seconds"] = self.polling_interval_seconds
        if self.skills:
            result["skills"] = self.skills
        return result


class PluginRegistry:
    """Discover and manage installed plugins."""

    def __init__(self, plugins_dir: Path) -> None:
        self._plugins_dir = plugins_dir
        self._plugins: dict[str, PluginManifest] = {}

    def discover(self) -> list[PluginManifest]:
        """Scan plugins_dir for plugin.json files and load manifests."""
        self._plugins.clear()
        if not self._plugins_dir.is_dir():
            log.debug("Plugins directory does not exist: %s", self._plugins_dir)
            return []

        found: list[PluginManifest] = []
        for child in sorted(self._plugins_dir.iterdir()):
            if not child.is_dir():
                continue
            manifest_path = child / "plugin.json"
            if not manifest_path.exists():
                continue
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = PluginManifest.from_dict(data, plugin_dir=child)
                self._plugins[manifest.name] = manifest
                found.append(manifest)
                log.info("Discovered plugin: %s v%s", manifest.name, manifest.version)
            except Exception:
                log.exception("Failed to load plugin manifest: %s", manifest_path)

        return found

    def get(self, name: str) -> PluginManifest | None:
        return self._plugins.get(name)

    def list_all(self) -> list[dict]:
        """Return summary of all plugins for API responses."""
        return [p.to_dict() for p in self._plugins.values()]

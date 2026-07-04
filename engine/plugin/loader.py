from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Callable, Awaitable

from .registry import PluginManifest

log = logging.getLogger(__name__)


def load_handler(manifest: PluginManifest) -> Callable[[dict], Awaitable[None]] | None:
    """Load the handler module from a plugin directory.

    Looks for handler.py with an async ``handle(event: dict)`` function.
    Returns the handle function, or None if not found.
    """
    handler_path = manifest.plugin_dir / "handler.py"
    if not handler_path.exists():
        log.warning("No handler.py in plugin %s", manifest.name)
        return None

    try:
        spec = importlib.util.spec_from_file_location(
            f"plugin_{manifest.name}_handler", handler_path
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        handle_fn: Any = getattr(mod, "handle", None)
        if handle_fn is None:
            log.warning("handler.py in %s has no handle() function", manifest.name)
            return None

        return handle_fn  # type: ignore[return-value]
    except Exception:
        log.exception("Failed to load handler for plugin %s", manifest.name)
        return None

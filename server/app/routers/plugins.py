from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..services.plugin_service import PluginService

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

# Singleton set during app lifespan; see main.py
_service: PluginService | None = None


def set_service(svc: PluginService) -> None:
    global _service
    _service = svc


def _svc() -> PluginService:
    if _service is None:
        raise HTTPException(503, "Plugin service not initialized")
    return _service


@router.get("")
async def list_plugins():
    """List all discovered plugins with their enabled state."""
    return _svc().list_plugins()


@router.post("/{name}/webhook")
async def receive_webhook(name: str, request: Request):
    """Webhook endpoint for plugin events."""
    svc = _svc()
    if svc.get_plugin(name) is None:
        raise HTTPException(404, f"Plugin '{name}' not found")

    payload = await request.json()

    # Pass GitHub event header if present
    gh_event = request.headers.get("X-GitHub-Event")
    if gh_event:
        payload["_github_event"] = gh_event

    result = await svc.handle_webhook(name, payload)
    if result.get("status") == "error":
        raise HTTPException(400, result.get("error", "handler error"))
    return result


@router.post("/{name}/enable")
async def enable_plugin(name: str):
    """Enable a plugin."""
    if not await _svc().enable_plugin(name):
        raise HTTPException(404, f"Plugin '{name}' not found")
    return {"status": "enabled", "plugin": name}


@router.post("/{name}/disable")
async def disable_plugin(name: str):
    """Disable a plugin."""
    if not await _svc().disable_plugin(name):
        raise HTTPException(404, f"Plugin '{name}' not found")
    return {"status": "disabled", "plugin": name}

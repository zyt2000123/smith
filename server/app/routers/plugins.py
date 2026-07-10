from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..services.plugin_service import PluginService

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

# Singleton set during app lifespan; see main.py
_service: PluginService | None = None


def set_service(svc: PluginService) -> None:
    global _service
    _service = svc


def get_plugin_service() -> PluginService:
    if _service is None:
        raise HTTPException(503, "Plugin service not initialized")
    return _service


@router.get("")
async def list_plugins(svc: PluginService = Depends(get_plugin_service)):
    """List all discovered plugins with their enabled state."""
    return svc.list_plugins()


@router.post("/{name}/webhook")
async def receive_webhook(
    name: str,
    request: Request,
    svc: PluginService = Depends(get_plugin_service),
):
    """Webhook endpoint for plugin events."""
    payload = await request.json()
    return await svc.receive_webhook(
        name,
        payload,
        github_event=request.headers.get("X-GitHub-Event"),
    )


@router.post("/{name}/enable")
async def enable_plugin(
    name: str,
    svc: PluginService = Depends(get_plugin_service),
):
    """Enable a plugin."""
    return await svc.enable_plugin_or_404(name)


@router.post("/{name}/disable")
async def disable_plugin(
    name: str,
    svc: PluginService = Depends(get_plugin_service),
):
    """Disable a plugin."""
    return await svc.disable_plugin_or_404(name)

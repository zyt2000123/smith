import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends

from common.database import close_db

from .infrastructure.auth import require_auth
from .infrastructure.database import get_app_db
from .routers import (
    agent,
    config,
    plugins,
)
from .services.scheduler import run_scheduler
from .services.plugin_service import PluginService

from common.config import BUILTIN_PLUGINS_DIR
from .services.engine_runtime import load_runtime_identity_catalog
_plugin_service = PluginService(BUILTIN_PLUGINS_DIR)
plugins.set_service(_plugin_service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_app_db()
    load_runtime_identity_catalog(force=True)
    scheduler_task = asyncio.create_task(run_scheduler())
    await _plugin_service.startup()
    yield
    await _plugin_service.shutdown()
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    await close_db()


app = FastAPI(title="Agent-Smith Server", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

app.include_router(agent.router, dependencies=[Depends(require_auth)])
app.include_router(config.router, dependencies=[Depends(require_auth)])
app.include_router(plugins.router, dependencies=[Depends(require_auth)])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}

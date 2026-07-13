import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends

from common.database import close_db

from .infrastructure.auth import get_local_token, require_auth
from .infrastructure.database import get_app_db
from .routers import (
    agent,
    config,
)
from .services.scheduler import run_scheduler

from .services.engine_runtime import close_shared_llm_clients, load_runtime_identity_catalog


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_local_token()
    await get_app_db()
    load_runtime_identity_catalog(force=True)
    scheduler_task = asyncio.create_task(run_scheduler())
    yield
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    await close_shared_llm_clients()
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


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}

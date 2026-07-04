import sys
from pathlib import Path

# Add common/ and engine/ to PYTHONPATH so their modules are importable
_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root / "common"))
sys.path.insert(0, str(_root / "engine"))
sys.path.insert(0, str(_root))

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.database import get_db, close_db
from .routers import employees, sessions, templates, tasks, files, config, auth, stats, auto_tasks
from .services.scheduler import run_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_db()
    scheduler_task = asyncio.create_task(run_scheduler())
    yield
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    await close_db()


app = FastAPI(title="Agent-Smith Server", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(employees.router)
app.include_router(sessions.router)
app.include_router(templates.router)
app.include_router(tasks.router)
app.include_router(files.router)
app.include_router(config.router)
app.include_router(auth.router)
app.include_router(stats.router)
app.include_router(auto_tasks.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}

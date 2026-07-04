from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db import get_db, close_db
from .routers import employees, sessions, templates, tasks, files, config

@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_db()
    yield
    await close_db()

app = FastAPI(title="Agent-Smith Server", version="0.1.0", lifespan=lifespan)

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

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}

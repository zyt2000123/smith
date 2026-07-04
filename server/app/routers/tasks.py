import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from ..db import get_db
from ..models.task import TaskCreate, TaskOut

router = APIRouter(prefix="/api/employees/{employee_id}/tasks", tags=["tasks"])

@router.get("", response_model=list[TaskOut])
async def list_tasks(employee_id: str):
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM tasks WHERE employee_id=? ORDER BY created_at DESC", (employee_id,))
    return [TaskOut(**dict(r)) for r in rows]

@router.post("", response_model=TaskOut, status_code=201)
async def create_task(employee_id: str, body: TaskCreate):
    db = await get_db()
    emp = await db.execute_fetchall("SELECT id FROM employees WHERE id=?", (employee_id,))
    if not emp:
        raise HTTPException(404, "Employee not found")
    tid = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO tasks (id, employee_id, type, title, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (tid, employee_id, body.type, body.title, "pending", now, now))
    await db.commit()
    return TaskOut(id=tid, employee_id=employee_id, type=body.type, title=body.title,
                   status="pending", session_id=None, created_at=now, updated_at=now)

import json, uuid, socket
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from ..db import get_db
from ..models.employee import EmployeeCreate, EmployeeUpdate, EmployeeOut
from ..employee_fs import init_employee_files, delete_employee_files
from ..agent_runtime import clear_agent
from ..templates.roles import ROLE_TEMPLATES

router = APIRouter(prefix="/api/employees", tags=["employees"])

def _row_to_out(row) -> EmployeeOut:
    return EmployeeOut(
        id=row["id"], name=row["name"], role=row["role"], device=row["device"],
        online=bool(row["online"]), description=row["description"],
        knowledge=json.loads(row["knowledge"]), environment=row["environment"],
        accent=row["accent"], created_at=row["created_at"],
    )

@router.get("", response_model=list[EmployeeOut])
async def list_employees():
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM employees ORDER BY created_at DESC")
    return [_row_to_out(r) for r in rows]

@router.post("", response_model=EmployeeOut, status_code=201)
async def create_employee(body: EmployeeCreate):
    db = await get_db()
    eid = uuid.uuid4().hex[:8]
    device = body.device or socket.gethostname()
    now = datetime.now(timezone.utc).isoformat()

    # ponytail: find matching template for identity/persona defaults
    tpl = next((t for t in ROLE_TEMPLATES if t["id"] == body.role or t["title"] == body.role), None)
    identity = tpl["identity"] if tpl else ""
    persona = tpl["persona"] if tpl else ""
    knowledge = body.knowledge or (tpl["knowledge"] if tpl else [])

    await db.execute(
        "INSERT INTO employees (id, name, role, device, online, description, knowledge, environment, accent, config_path, created_at) VALUES (?,?,?,?,1,?,?,?,?,?,?)",
        (eid, body.name, body.role, device, body.description, json.dumps(knowledge, ensure_ascii=False),
         body.environment, body.accent, f"~/.agent-smith/employees/{eid}", now),
    )
    await db.commit()
    init_employee_files(eid, name=body.name, role=body.role, description=body.description,
                        identity=identity, persona=persona, knowledge=knowledge)
    row = await db.execute_fetchall("SELECT * FROM employees WHERE id=?", (eid,))
    return _row_to_out(row[0])

@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(employee_id: str):
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM employees WHERE id=?", (employee_id,))
    if not rows:
        raise HTTPException(404, "Employee not found")
    return _row_to_out(rows[0])

@router.put("/{employee_id}", response_model=EmployeeOut)
async def update_employee(employee_id: str, body: EmployeeUpdate):
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM employees WHERE id=?", (employee_id,))
    if not rows:
        raise HTTPException(404, "Employee not found")
    updates, params = [], []
    for field in ["name", "role", "description", "device", "accent"]:
        val = getattr(body, field, None)
        if val is not None:
            updates.append(f"{field}=?")
            params.append(val)
    if body.knowledge is not None:
        updates.append("knowledge=?")
        params.append(json.dumps(body.knowledge, ensure_ascii=False))
    if body.online is not None:
        updates.append("online=?")
        params.append(int(body.online))
    if not updates:
        return _row_to_out(rows[0])
    params.append(employee_id)
    await db.execute(f"UPDATE employees SET {', '.join(updates)} WHERE id=?", params)
    await db.commit()
    clear_agent(employee_id)
    rows = await db.execute_fetchall("SELECT * FROM employees WHERE id=?", (employee_id,))
    return _row_to_out(rows[0])

@router.delete("/{employee_id}", status_code=204)
async def delete_employee(employee_id: str):
    db = await get_db()
    rows = await db.execute_fetchall("SELECT id FROM employees WHERE id=?", (employee_id,))
    if not rows:
        raise HTTPException(404, "Employee not found")
    await db.execute("DELETE FROM employees WHERE id=?", (employee_id,))
    await db.commit()
    clear_agent(employee_id)
    delete_employee_files(employee_id)

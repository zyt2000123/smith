from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..employee_fs import read_employee_file, write_employee_file, employee_dir

router = APIRouter(prefix="/api/employees/{employee_id}/files", tags=["files"])

ALLOWED_FILES = {"identity.md", "persona.md", "bible.md", "config.yaml"}

class FileContent(BaseModel):
    content: str

@router.get("/{filename}")
async def get_file(employee_id: str, filename: str):
    if filename not in ALLOWED_FILES:
        raise HTTPException(400, f"File not allowed. Allowed: {ALLOWED_FILES}")
    content = read_employee_file(employee_id, filename)
    if content is None:
        raise HTTPException(404, "File not found")
    return {"filename": filename, "content": content}

@router.put("/{filename}")
async def update_file(employee_id: str, filename: str, body: FileContent):
    if filename not in ALLOWED_FILES:
        raise HTTPException(400, f"File not allowed. Allowed: {ALLOWED_FILES}")
    if not employee_dir(employee_id).exists():
        raise HTTPException(404, "Employee not found")
    write_employee_file(employee_id, filename, body.content)
    return {"filename": filename, "content": body.content}

@router.get("")
async def list_files(employee_id: str):
    d = employee_dir(employee_id)
    if not d.exists():
        raise HTTPException(404, "Employee not found")
    return [{"filename": f.name, "size": f.stat().st_size}
            for f in sorted(d.iterdir()) if f.is_file()]

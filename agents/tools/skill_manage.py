from __future__ import annotations

"""Skill management tool provider — list, read, create, edit, patch, and version skills.

Built-in skills (under agents/skills/) are READ-ONLY.
Only employee-installed skills (under ~/.agent-smith/employees/<id>/skills/)
can be modified.
"""

import os
import re
from pathlib import Path

import yaml

TOOL_META = {
    "name": "skill_manage",
    "description": (
        "Manage employee skills: list, get, create, edit, patch, versions, rollback. "
        "Built-in skills are read-only; only employee-installed skills can be modified."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "get", "create", "edit", "patch", "versions", "rollback"],
                "description": "The skill management operation to perform",
            },
            "employee_id": {
                "type": "string",
                "description": "Employee identifier (used to locate skills directory)",
            },
            "skill_name": {
                "type": "string",
                "description": "Skill name (required for get/create/edit/patch/versions/rollback)",
            },
            "content": {
                "type": "string",
                "description": "Full SKILL.md content (required for create/edit)",
            },
            "section": {
                "type": "string",
                "description": "Section heading to patch, e.g. '## Process' (required for patch)",
            },
            "section_content": {
                "type": "string",
                "description": "New content for the section (required for patch)",
            },
            "version_id": {
                "type": "string",
                "description": "Version id (required for rollback)",
            },
        },
        "required": ["action", "employee_id"],
    },
}

# Builtin skills directory — resolved relative to this file
_BUILTIN_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")


def _employee_skills_dir(employee_id: str) -> Path:
    safe_id = Path(employee_id).name
    return Path.home() / ".agent-smith" / "employees" / safe_id / "skills"


def _is_builtin(skill_name: str) -> bool:
    safe = os.path.basename(skill_name)
    return os.path.isfile(os.path.join(_BUILTIN_SKILLS_DIR, safe, "SKILL.md"))


def _parse_frontmatter(raw: str) -> dict:
    """Extract YAML frontmatter from SKILL.md content."""
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            return yaml.safe_load(parts[1]) or {}
    return {}


def _list_all_skills(employee_id: str) -> list[dict]:
    """List builtin + employee-installed skills with metadata."""
    skills: list[dict] = []

    # Builtin
    builtin_dir = Path(_BUILTIN_SKILLS_DIR)
    if builtin_dir.is_dir():
        for child in sorted(builtin_dir.iterdir()):
            sf = child / "SKILL.md"
            if sf.is_file():
                meta = _parse_frontmatter(sf.read_text(encoding="utf-8"))
                skills.append({
                    "name": meta.get("name", child.name),
                    "description": meta.get("description", ""),
                    "version": meta.get("version", "0.1.0"),
                    "source": "builtin",
                })

    # Employee-installed
    emp_dir = _employee_skills_dir(employee_id)
    if emp_dir.is_dir():
        for child in sorted(emp_dir.iterdir()):
            sf = child / "SKILL.md"
            if sf.is_file():
                meta = _parse_frontmatter(sf.read_text(encoding="utf-8"))
                skills.append({
                    "name": meta.get("name", child.name),
                    "description": meta.get("description", ""),
                    "version": meta.get("version", "0.1.0"),
                    "source": "employee",
                })

    return skills


def _get_skill_content(employee_id: str, skill_name: str) -> tuple[str, str]:
    """Return (content, source) for a skill. Checks employee first, then builtin."""
    safe = Path(skill_name).name

    # Employee-installed first
    emp_path = _employee_skills_dir(employee_id) / safe / "SKILL.md"
    if emp_path.is_file():
        return emp_path.read_text(encoding="utf-8"), "employee"

    # Builtin
    builtin_path = Path(_BUILTIN_SKILLS_DIR) / safe / "SKILL.md"
    if builtin_path.is_file():
        return builtin_path.read_text(encoding="utf-8"), "builtin"

    return "", ""


def _patch_section(raw: str, section_heading: str, new_content: str) -> str:
    """Replace a markdown section's content, preserving everything else.

    *section_heading* should be a heading like '## Process' or '### Step 1'.
    """
    # Determine heading level from the target
    match = re.match(r"^(#{1,6})\s+", section_heading)
    if not match:
        raise ValueError(f"Invalid section heading: {section_heading}")
    level = len(match.group(1))

    lines = raw.split("\n")
    result: list[str] = []
    i = 0
    patched = False

    while i < len(lines):
        line = lines[i]
        # Check if this line matches the target section heading
        if not patched and line.strip() == section_heading.strip():
            # Emit the heading
            result.append(line)
            i += 1
            # Skip old content until we hit a heading of same or higher level, or EOF
            while i < len(lines):
                next_line = lines[i]
                heading_match = re.match(r"^(#{1,6})\s+", next_line)
                if heading_match and len(heading_match.group(1)) <= level:
                    break
                i += 1
            # Insert new content
            result.append(new_content.rstrip())
            result.append("")
            patched = True
        else:
            result.append(line)
            i += 1

    if not patched:
        raise ValueError(f"Section '{section_heading}' not found in SKILL.md")

    return "\n".join(result)


async def execute(
    *,
    action: str,
    employee_id: str,
    skill_name: str | None = None,
    content: str | None = None,
    section: str | None = None,
    section_content: str | None = None,
    version_id: str | None = None,
) -> str:
    # Lazy import to avoid circular deps at module level
    from engine.skill.store import SkillStore

    emp_dir = _employee_skills_dir(employee_id)
    store = SkillStore(emp_dir)

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------
    if action == "list":
        skills = _list_all_skills(employee_id)
        if not skills:
            return "No skills found."
        lines = [f"Found {len(skills)} skill(s):\n"]
        for s in skills:
            tag = "[builtin]" if s["source"] == "builtin" else "[employee]"
            lines.append(f"- {tag} {s['name']} v{s['version']}: {s['description']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------
    if action == "get":
        if not skill_name:
            return "Error: 'skill_name' is required for get action"
        raw, source = _get_skill_content(employee_id, skill_name)
        if not raw:
            return f"Error: skill '{skill_name}' not found"
        return f"# Skill: {skill_name} [{source}]\n\n{raw}"

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------
    if action == "create":
        if not skill_name:
            return "Error: 'skill_name' is required for create action"
        if not content:
            return "Error: 'content' is required for create action"
        if _is_builtin(skill_name):
            return f"Error: '{skill_name}' is a built-in skill name. Choose a different name."

        safe = Path(skill_name).name
        skill_dir = emp_dir / safe
        skill_file = skill_dir / "SKILL.md"
        if skill_file.is_file():
            return f"Error: skill '{skill_name}' already exists. Use 'edit' to modify it."

        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(content, encoding="utf-8")
        return f"OK: created skill '{skill_name}' at {skill_file}"

    # ------------------------------------------------------------------
    # edit (full rewrite)
    # ------------------------------------------------------------------
    if action == "edit":
        if not skill_name:
            return "Error: 'skill_name' is required for edit action"
        if not content:
            return "Error: 'content' is required for edit action"
        if _is_builtin(skill_name):
            return "Error: built-in skills are read-only. Cannot edit."

        safe = Path(skill_name).name
        skill_file = emp_dir / safe / "SKILL.md"
        if not skill_file.is_file():
            return f"Error: skill '{skill_name}' not found in employee skills. Use 'create' first."

        # Auto-save version before editing
        old_content = skill_file.read_text(encoding="utf-8")
        vid = await store.save_version(skill_name, old_content)

        skill_file.write_text(content, encoding="utf-8")
        return f"OK: edited skill '{skill_name}' (previous version saved as {vid})"

    # ------------------------------------------------------------------
    # patch (section-level edit)
    # ------------------------------------------------------------------
    if action == "patch":
        if not skill_name:
            return "Error: 'skill_name' is required for patch action"
        if not section:
            return "Error: 'section' is required for patch action"
        if section_content is None:
            return "Error: 'section_content' is required for patch action"
        if _is_builtin(skill_name):
            return "Error: built-in skills are read-only. Cannot patch."

        safe = Path(skill_name).name
        skill_file = emp_dir / safe / "SKILL.md"
        if not skill_file.is_file():
            return f"Error: skill '{skill_name}' not found in employee skills"

        old_content = skill_file.read_text(encoding="utf-8")

        # Auto-save version before patching
        vid = await store.save_version(skill_name, old_content)

        try:
            new_content = _patch_section(old_content, section, section_content)
        except ValueError as e:
            return f"Error: {e}"

        skill_file.write_text(new_content, encoding="utf-8")
        return f"OK: patched section '{section}' in skill '{skill_name}' (previous version saved as {vid})"

    # ------------------------------------------------------------------
    # versions
    # ------------------------------------------------------------------
    if action == "versions":
        if not skill_name:
            return "Error: 'skill_name' is required for versions action"

        versions = await store.list_versions(skill_name)
        if not versions:
            return f"No versions found for skill '{skill_name}'"

        lines = [f"Versions for '{skill_name}' ({len(versions)}):"]
        for v in versions:
            lines.append(f"- {v['version_id']}  ({v['size']} bytes)")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # rollback
    # ------------------------------------------------------------------
    if action == "rollback":
        if not skill_name:
            return "Error: 'skill_name' is required for rollback action"
        if not version_id:
            return "Error: 'version_id' is required for rollback action"
        if _is_builtin(skill_name):
            return "Error: built-in skills are read-only. Cannot rollback."

        ok = await store.rollback(skill_name, version_id)
        if not ok:
            return f"Error: version '{version_id}' not found for skill '{skill_name}'"
        return f"OK: rolled back skill '{skill_name}' to version '{version_id}'"

    return f"Error: unknown action '{action}'. Use: list, get, create, edit, patch, versions, rollback"

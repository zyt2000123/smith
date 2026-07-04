"""Skill loader tool provider — loads a SKILL.md by name from the skills directory."""

import os

TOOL_META = {
    "name": "skill_load",
    "description": "Load a skill definition (SKILL.md) by name. Returns the skill's process and guidelines.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Skill name (e.g., 'planning', 'code-review', 'sde-debug')"
            }
        },
        "required": ["name"]
    }
}

# Default skills directory — resolved relative to this file
_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")


async def execute(*, name: str) -> str:
    safe_name = os.path.basename(name)
    skill_path = os.path.join(_SKILLS_DIR, safe_name, "SKILL.md")

    if not os.path.isfile(skill_path):
        available = []
        if os.path.isdir(_SKILLS_DIR):
            for entry in sorted(os.listdir(_SKILLS_DIR)):
                candidate = os.path.join(_SKILLS_DIR, entry, "SKILL.md")
                if os.path.isfile(candidate):
                    available.append(entry)
        available_str = ", ".join(available) if available else "(none found)"
        return (
            f"Error: skill '{safe_name}' not found at {skill_path}\n"
            f"Available skills: {available_str}"
        )

    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return f"Error reading skill: {e}"

    return f"# Skill: {safe_name}\n\n{content}"

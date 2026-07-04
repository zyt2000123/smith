from __future__ import annotations

import re


def render_placeholders(text: str, variables: dict) -> str:
    """Replace {{key}} placeholders with values from *variables*.

    Unknown placeholders are left untouched.
    """
    def _replace(m: re.Match) -> str:
        key = m.group(1).strip()
        return str(variables[key]) if key in variables else m.group(0)

    return re.sub(r"\{\{(.+?)\}\}", _replace, text)

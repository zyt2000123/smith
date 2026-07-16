"""Coding-domain step conditions.

Content layer: loaded by ``engine.execution.skill_chain.load_gate_content``.
The module-level ``CONDITIONS`` mapping is merged into the condition
registry that pipeline YAML ``condition:`` keys resolve against.
"""

from __future__ import annotations

import re


def needs_architecture(ctx: dict) -> bool:
    """Skip architecture for small, single-module changes."""
    plan_output = ctx.get(output_key("planning"), "")
    file_refs = re.findall(r'[\w/]+\.\w{1,5}', plan_output)
    return len(set(file_refs)) >= 3


CONDITIONS = {
    "needs_architecture": needs_architecture,
}

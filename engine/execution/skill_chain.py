from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .gate import (
    Gate,
    PlanningGate,
    ReviewGate,
    RootCauseGate,
    SkillRubricGate,
    TestGate,
    ValidationGate,
)


@dataclass
class SkillNode:
    skill_name: str
    gate: Gate
    condition: Callable[[dict], bool] | None = None  # skip if returns False


class SkillChain:
    def __init__(
        self,
        nodes: list[SkillNode],
        backtrack_map: dict[str, str] | None = None,
    ) -> None:
        self.nodes = nodes
        self.backtrack_map: dict[str, str] = backtrack_map or {}

    @staticmethod
    def feature_chain() -> SkillChain:
        """Predefined skill chain for feature development (QoderWake order)."""

        def _needs_architecture(ctx: dict) -> bool:
            """Skip architecture for small, single-module changes."""
            # Condition: 3+ files touched or cross-module work
            plan_output = ctx.get("planning_output", "")
            import re
            file_refs = re.findall(r'[\w/]+\.\w{1,5}', plan_output)
            return len(set(file_refs)) >= 3

        return SkillChain(
            nodes=[
                SkillNode(skill_name="planning", gate=PlanningGate()),
                SkillNode(skill_name="architecture", gate=SkillRubricGate(), condition=_needs_architecture),
                SkillNode(skill_name="testing-strategy", gate=TestGate()),
                SkillNode(skill_name="change-validation", gate=ValidationGate()),
                SkillNode(skill_name="code-review", gate=ReviewGate()),
            ],
            backtrack_map={
                "change-validation": "planning",
                "code-review": "change-validation",
                "testing-strategy": "planning",
            },
        )

    @staticmethod
    def bugfix_chain() -> SkillChain:
        """Predefined skill chain for bug fixing (QoderWake order)."""
        return SkillChain(
            nodes=[
                SkillNode(skill_name="sde-debug", gate=RootCauseGate()),
                SkillNode(skill_name="planning", gate=PlanningGate()),
                SkillNode(skill_name="testing-strategy", gate=TestGate()),
                SkillNode(skill_name="change-validation", gate=ValidationGate()),
                SkillNode(skill_name="code-review", gate=ReviewGate()),
            ],
            backtrack_map={
                "change-validation": "planning",
                "code-review": "change-validation",
                "testing-strategy": "planning",
            },
        )

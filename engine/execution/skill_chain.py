from __future__ import annotations

import re as _re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Collection

from .gate import (
    ContractAlignmentGate,
    DesignGate,
    Gate,
    PlanningGate,
    ReviewGate,
    RootCauseGate,
    SkillRubricGate,
    TestGate,
    UnderstandingGate,
    ValidationGate,
    planning_gate_with_llm,
    validation_gate_with_llm,
)

_GATE_MAP: dict[str, Callable[[], Gate]] = {
    "understand": UnderstandingGate,
    "planning": planning_gate_with_llm,
    "architecture": DesignGate,
    "testing-strategy": TestGate,
    "contract-alignment": ContractAlignmentGate,
    "change-validation": validation_gate_with_llm,
    "code-review": ReviewGate,
    "sde-debug": RootCauseGate,
}

_DEFAULT_BACKTRACK: dict[str, str] = {
    "contract-alignment": "planning",
    "change-validation": "planning",
    "code-review": "change-validation",
    "testing-strategy": "planning",
}


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

    def for_available_skills(self, available: Collection[str]) -> SkillChain | None:
        """Keep only nodes backed by a loaded skill, or disable the chain."""
        available_names = set(available)
        nodes = [node for node in self.nodes if node.skill_name in available_names]
        if not nodes:
            return None

        node_names = {node.skill_name for node in nodes}
        backtrack_map = {
            source: target
            for source, target in self.backtrack_map.items()
            if source in node_names and target in node_names
        }
        return SkillChain(nodes=nodes, backtrack_map=backtrack_map)

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
                SkillNode(skill_name="understand", gate=UnderstandingGate()),
                SkillNode(skill_name="full-stack-product", gate=SkillRubricGate()),
                SkillNode(skill_name="planning", gate=planning_gate_with_llm()),
                SkillNode(skill_name="architecture", gate=DesignGate(), condition=_needs_architecture),
                SkillNode(skill_name="testing-strategy", gate=TestGate()),
                SkillNode(skill_name="contract-alignment", gate=ContractAlignmentGate()),
                SkillNode(skill_name="change-validation", gate=validation_gate_with_llm()),
                SkillNode(skill_name="code-review", gate=ReviewGate()),
            ],
            backtrack_map=_DEFAULT_BACKTRACK,
        )

    @staticmethod
    def refactor_chain() -> SkillChain:
        return SkillChain(
            nodes=[
                SkillNode(skill_name="planning", gate=planning_gate_with_llm()),
                SkillNode(skill_name="testing-strategy", gate=TestGate()),
                SkillNode(skill_name="change-validation", gate=validation_gate_with_llm()),
                SkillNode(skill_name="code-review", gate=ReviewGate()),
            ],
            backtrack_map=_DEFAULT_BACKTRACK,
        )

    @classmethod
    def from_workflow_md(cls, path: Path, route: str) -> SkillChain | None:
        """Parse a workflow.md and build a SkillChain for the given route.

        Looks for ```-fenced lines like: planning → architecture(仅大型变更) → code-review
        under a heading containing the route name (e.g. "### Feature 路由").
        """
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")

        # Find the section for this route
        pattern = _re.compile(
            rf"###?\s*{_re.escape(route)}.*?```\s*\n(.+?)\n\s*```",
            _re.IGNORECASE | _re.DOTALL,
        )
        m = pattern.search(text)
        if not m:
            return None

        chain_line = m.group(1).strip().splitlines()[0]
        raw_names = [s.strip() for s in _re.split(r"\s*→\s*", chain_line) if s.strip()]

        nodes = []
        for raw in raw_names:
            clean = _re.sub(r"\(.*?\)", "", raw).strip()
            condition = None
            if "仅" in raw or "only" in raw.lower() or "条件" in raw:
                def _needs_architecture(ctx: dict) -> bool:
                    plan_output = ctx.get("planning_output", "")
                    file_refs = _re.findall(r"[\w/]+\.\w{1,5}", plan_output)
                    return len(set(file_refs)) >= 3
                condition = _needs_architecture

            gate_factory = _GATE_MAP.get(clean, SkillRubricGate)
            gate = gate_factory() if callable(gate_factory) else gate_factory
            nodes.append(SkillNode(skill_name=clean, gate=gate, condition=condition))

        if not nodes:
            return None
        return cls(nodes=nodes, backtrack_map=_DEFAULT_BACKTRACK)

    @staticmethod
    def bugfix_chain() -> SkillChain:
        """Predefined skill chain for bug fixing (QoderWake order)."""
        return SkillChain(
            nodes=[
                SkillNode(skill_name="understand", gate=UnderstandingGate()),
                SkillNode(skill_name="sde-debug", gate=RootCauseGate()),
                SkillNode(skill_name="planning", gate=planning_gate_with_llm()),
                SkillNode(skill_name="testing-strategy", gate=TestGate()),
                SkillNode(skill_name="contract-alignment", gate=ContractAlignmentGate()),
                SkillNode(skill_name="change-validation", gate=validation_gate_with_llm()),
                SkillNode(skill_name="code-review", gate=ReviewGate()),
            ],
            backtrack_map=_DEFAULT_BACKTRACK,
        )

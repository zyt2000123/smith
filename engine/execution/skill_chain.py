from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

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

logger = logging.getLogger(__name__)

GATE_REGISTRY: dict[str, Callable[[], Gate]] = {
    "understanding": UnderstandingGate,
    "planning": PlanningGate,
    "planning_llm": planning_gate_with_llm,
    "design": DesignGate,
    "test": TestGate,
    "contract_alignment": ContractAlignmentGate,
    "validation_llm": validation_gate_with_llm,
    "review": ReviewGate,
    "root_cause": RootCauseGate,
    "rubric": SkillRubricGate,
}


def _needs_architecture(ctx: dict) -> bool:
    """Skip architecture for small, single-module changes."""
    plan_output = ctx.get("planning_output", "")
    import re
    file_refs = re.findall(r'[\w/]+\.\w{1,5}', plan_output)
    return len(set(file_refs)) >= 3


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

    # ------------------------------------------------------------------
    # YAML-based pipeline loading
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Path) -> SkillChain | None:
        """Build a SkillChain from a pipeline YAML definition file."""
        if not path.is_file():
            return None
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("failed to parse pipeline yaml: %s", path)
            return None
        if not isinstance(data, dict):
            return None

        steps = data.get("steps")
        if not isinstance(steps, list) or not steps:
            return None

        nodes: list[SkillNode] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            skill_name = step.get("skill")
            if not isinstance(skill_name, str) or not skill_name:
                continue
            gate_key = step.get("gate", "rubric")
            gate_factory = GATE_REGISTRY.get(gate_key, SkillRubricGate)
            gate = gate_factory() if callable(gate_factory) else gate_factory

            condition = None
            cond_key = step.get("condition")
            if cond_key == "needs_architecture":
                condition = _needs_architecture

            nodes.append(SkillNode(skill_name=skill_name, gate=gate, condition=condition))

        if not nodes:
            return None

        backtrack = data.get("backtrack")
        backtrack_map = dict(backtrack) if isinstance(backtrack, dict) else {}
        return cls(nodes=nodes, backtrack_map=backtrack_map)

    @classmethod
    def load_pipelines(cls, pipelines_dir: Path) -> dict[str, "SkillChain"]:
        """Load all pipeline YAML files from a directory, keyed by route name."""
        result: dict[str, SkillChain] = {}
        if not pipelines_dir.is_dir():
            return result
        for yaml_file in sorted(pipelines_dir.glob("*.yaml")):
            chain = cls.from_yaml(yaml_file)
            if chain is None:
                continue
            try:
                import yaml
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                route = data.get("route", yaml_file.stem)
            except Exception:
                route = yaml_file.stem
            result[route] = chain
        return result

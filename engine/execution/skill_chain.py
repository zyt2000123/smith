from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .gate import Gate

logger = logging.getLogger(__name__)

# Gate and condition implementations are content, not engine code.  The
# registries start empty and are populated by load_gate_content(), which
# scans <agents_dir>/gates/**.py (module-level GATES) and
# <agents_dir>/conditions/**.py (module-level CONDITIONS).  from_yaml stays
# a pure lookup that fails loudly on an unknown key instead of silently
# degrading.
GATE_REGISTRY: dict[str, Callable[[], Gate]] = {}
CONDITION_REGISTRY: dict[str, Callable[[dict], bool]] = {}

_LOADED_CONTENT_DIRS: set[Path] = set()


class GateContentError(ValueError):
    """Raised when gate/condition content files are invalid."""


def load_gate_content(agents_dir: Path) -> None:
    """Populate the gate/condition registries from content directories.

    Scans ``<agents_dir>/gates/**/*.py`` for module-level ``GATES`` mappings
    and ``<agents_dir>/conditions/**/*.py`` for ``CONDITIONS``.  Idempotent
    per directory.  Invalid content fails loudly: a broken gate file must
    surface at startup, not as a confusing "unknown gate" at pipeline parse.
    """
    root = agents_dir.resolve()
    if root in _LOADED_CONTENT_DIRS:
        return
    _scan_content_dir(root / "gates", "GATES", GATE_REGISTRY)
    _scan_content_dir(root / "conditions", "CONDITIONS", CONDITION_REGISTRY)
    _LOADED_CONTENT_DIRS.add(root)


def _scan_content_dir(content_dir: Path, attr: str, registry: dict) -> None:
    if not content_dir.is_dir():
        return
    for py_file in sorted(content_dir.rglob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"agent_smith_content_{py_file.parent.name}_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                raise GateContentError(f"cannot load module spec for {py_file}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except GateContentError:
            raise
        except Exception as exc:
            raise GateContentError(f"failed to load gate content {py_file}: {exc}") from exc

        mapping = getattr(mod, attr, None)
        if mapping is None:
            continue
        if not isinstance(mapping, dict):
            raise GateContentError(f"{py_file}: {attr} must be a dict")
        for key, factory in mapping.items():
            if not isinstance(key, str) or not key:
                raise GateContentError(f"{py_file}: {attr} keys must be non-empty strings")
            if not callable(factory):
                raise GateContentError(f"{py_file}: {attr}[{key!r}] must be callable")
            if key in registry and registry[key] is not factory:
                raise GateContentError(f"{py_file}: duplicate {attr} key {key!r}")
            registry[key] = factory


def _resolve_gate(gate_key: str, path: Path, where: str) -> Gate:
    if gate_key not in GATE_REGISTRY:
        raise ValueError(
            f"{path.name}: unknown gate {gate_key!r} in {where}; "
            f"valid gates: {', '.join(sorted(GATE_REGISTRY))}"
        )
    gate_factory = GATE_REGISTRY[gate_key]
    return gate_factory() if callable(gate_factory) else gate_factory


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
        base_gates: list[Gate] | None = None,
    ) -> None:
        self.nodes = nodes
        self.backtrack_map: dict[str, str] = backtrack_map or {}
        # 兜底层：每个节点产出先过 base_gates，再过节点自己的 gate。
        # 由 pipeline YAML 顶层 base_gate/base_gates 声明，引擎不预置。
        self.base_gates: list[Gate] = list(base_gates or [])

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
            gate = _resolve_gate(gate_key, path, f"step {skill_name!r}")

            condition = None
            cond_key = step.get("condition")
            if cond_key is not None:
                if cond_key not in CONDITION_REGISTRY:
                    raise ValueError(
                        f"{path.name}: unknown condition {cond_key!r} in step {skill_name!r}; "
                        f"valid conditions: {', '.join(sorted(CONDITION_REGISTRY))}"
                    )
                condition = CONDITION_REGISTRY[cond_key]

            nodes.append(SkillNode(skill_name=skill_name, gate=gate, condition=condition))

        if not nodes:
            return None

        base_keys = data.get("base_gates", data.get("base_gate"))
        if isinstance(base_keys, str):
            base_keys = [base_keys]
        base_gates: list[Gate] = []
        if base_keys is not None:
            if not isinstance(base_keys, list):
                raise ValueError(
                    f"{path.name}: base_gate(s) must be a gate key or a list of gate keys"
                )
            for key in base_keys:
                if not isinstance(key, str):
                    raise ValueError(f"{path.name}: base_gate entries must be strings")
                base_gates.append(_resolve_gate(key, path, "base_gates"))

        backtrack = data.get("backtrack")
        backtrack_map = dict(backtrack) if isinstance(backtrack, dict) else {}
        return cls(nodes=nodes, backtrack_map=backtrack_map, base_gates=base_gates)

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

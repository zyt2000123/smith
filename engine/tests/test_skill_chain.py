from pathlib import Path

import pytest

from engine.execution.skill_chain import SkillChain


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "pipeline.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_unknown_gate_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "steps:\n  - skill: understand\n    gate: reviewww\n")
    with pytest.raises(ValueError, match="unknown gate"):
        SkillChain.from_yaml(path)


def test_unknown_condition_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "steps:\n  - skill: architecture\n    gate: design\n    condition: nope\n",
    )
    with pytest.raises(ValueError, match="unknown condition"):
        SkillChain.from_yaml(path)


def test_valid_pipeline_still_loads(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "steps:\n"
        "  - skill: understand\n"
        "    gate: understanding\n"
        "  - skill: architecture\n"
        "    gate: design\n"
        "    condition: needs_architecture\n",
    )
    chain = SkillChain.from_yaml(path)
    assert chain is not None
    assert [n.skill_name for n in chain.nodes] == ["understand", "architecture"]
    assert chain.nodes[1].condition is not None


def test_gate_defaults_to_rubric_when_omitted(tmp_path: Path) -> None:
    path = _write(tmp_path, "steps:\n  - skill: understand\n")
    chain = SkillChain.from_yaml(path)
    assert chain is not None
    assert chain.nodes[0].gate is not None

"""UnderstandingGate / ContractAlignmentGate 单测 + 技能链接线检查。"""
import asyncio

from engine.execution.gate import ContractAlignmentGate, UnderstandingGate
from engine.execution.skill_chain import SkillChain


def _check(gate, output, context=None):
    return asyncio.run(gate.check(output, context or {}))


def test_understanding_passes_with_restatement_and_boundaries():
    output = (
        "需求复述：用户希望在聊天输入框支持选择工作目录并拖拽文件。"
        "边界条件：仅本机路径在范围内，远程文件不包括；约束：后端接口保持向后兼容。"
    )
    assert _check(UnderstandingGate(), output).verdict == "pass"


def test_understanding_fails_when_no_boundaries():
    output = "需求是给输入框加一个按钮，用户想要更方便的操作，这个功能目标很明确。"
    result = _check(UnderstandingGate(), output)
    assert result.verdict == "fail"
    assert "boundary" in result.reason


def test_understanding_fails_on_short_output():
    assert _check(UnderstandingGate(), "明白了，就是加个按钮。").verdict == "fail"


def test_contract_alignment_passes_with_verdict_and_refs():
    output = (
        "对照计划逐条检查：第 1 步 修改 task_router.py — 一致；"
        "第 2 步 新增 gate.py 类 — 一致。总体结论：与计划一致，可以继续。"
    )
    ctx = {"planning_output": "1. 修改 task_router.py 2. 新增 gate.py 类"}
    assert _check(ContractAlignmentGate(), output, ctx).verdict == "pass"


def test_contract_alignment_fails_without_verdict():
    output = "我看了一下实现方案，感觉整体还行，没有什么大问题。"
    result = _check(ContractAlignmentGate(), output, {"planning_output": "1. xxx"})
    assert result.verdict == "fail"


def test_feature_chain_wiring():
    names = [n.skill_name for n in SkillChain.feature_chain().nodes]
    assert names == [
        "understand", "full-stack-product", "planning", "architecture", "testing-strategy",
        "contract-alignment", "change-validation", "code-review",
    ]
    assert SkillChain.feature_chain().backtrack_map["contract-alignment"] == "planning"


def test_bugfix_chain_wiring():
    names = [n.skill_name for n in SkillChain.bugfix_chain().nodes]
    assert names == [
        "understand", "sde-debug", "planning", "testing-strategy",
        "contract-alignment", "change-validation", "code-review",
    ]


def test_skill_chain_keeps_only_loaded_skills_and_valid_backtracks():
    chain = SkillChain.feature_chain().for_available_skills(
        {"planning", "change-validation", "code-review"}
    )

    assert chain is not None
    assert [node.skill_name for node in chain.nodes] == [
        "planning", "change-validation", "code-review",
    ]
    assert chain.backtrack_map == {
        "change-validation": "planning",
        "code-review": "change-validation",
    }


def test_skill_chain_is_disabled_when_no_skills_are_loaded():
    assert SkillChain.feature_chain().for_available_skills(set()) is None


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failures else 0)

"""Evaluation-sensitive detection — flags benchmark / grading scenarios.

Moved from ``engine.execution.task_router`` where it was misplaced among
routing logic.  This is a safety/integrity concern: it detects when a
request might be part of a benchmark or grading pipeline and injects
guidance to prevent result-gaming.
"""

from __future__ import annotations

import re

# 词表刻意收窄，避免"测试用例"等日常开发用语误报；误报的代价只是多一段谨慎提示。
_EVAL_SENSITIVE = re.compile(
    r"(?i)(benchmark|leaderboard|autograder|\bgrader\b|评测|测评|跑分|判分|评分标准|阅卷"
    r"|make (?:all )?(?:the )?tests? pass|让(?:所有)?测试(?:用例)?通过|通过率|pass rate)"
)

EVAL_SENSITIVE_GUIDANCE = (
    "[评测敏感模式]\n"
    "检测到当前任务可能处于评测/基准测试场景。行为约束：\n"
    "- 诚实解决任务本身，而不是让指标\"看起来通过\"\n"
    "- 禁止硬编码测试期望值、针对测试用例打补丁、或修改测试/评分文件\n"
    "- 如果无法真正解决，如实说明失败原因，不得伪造结果"
)


def detect_eval_sensitive(user_message: str) -> bool:
    """Return whether a request needs evaluation-integrity guidance."""
    return bool(_EVAL_SENSITIVE.search(user_message))

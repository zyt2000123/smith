from __future__ import annotations

from enum import Enum


class TaskType(Enum):
    BUGFIX = "bugfix"
    FEATURE = "feature"
    DIRECT = "direct"


_BUGFIX_KEYWORDS = (
    "bug", "fix", "error", "crash", "broken", "issue", "debug",
    "traceback", "exception", "fail", "regression", "wrong",
    "修复", "修改", "报错", "异常", "崩溃", "出错", "排查",
)

_FEATURE_KEYWORDS = (
    "add", "create", "build", "implement", "new feature", "design",
    "develop", "integrate", "support", "enable",
    "新增", "实现", "开发", "创建", "添加", "搭建", "接入", "支持",
)


def route_task(user_message: str) -> TaskType:
    """Classify a user message into a task type via keyword matching."""
    lower = user_message.lower()

    bug_score = sum(1 for kw in _BUGFIX_KEYWORDS if kw in lower)
    feat_score = sum(1 for kw in _FEATURE_KEYWORDS if kw in lower)

    if bug_score > feat_score and bug_score > 0:
        return TaskType.BUGFIX
    if feat_score > bug_score and feat_score > 0:
        return TaskType.FEATURE
    return TaskType.DIRECT

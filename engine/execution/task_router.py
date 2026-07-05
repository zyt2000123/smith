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


def _check_override(msg: str) -> tuple[TaskType | None, str]:
    """If message starts with [bugfix]/[feature]/[direct], return that type and stripped message."""
    lower = msg.lstrip().lower()
    for tag, tt in [("[bugfix]", TaskType.BUGFIX), ("[feature]", TaskType.FEATURE), ("[direct]", TaskType.DIRECT)]:
        if lower.startswith(tag):
            return tt, msg.lstrip()[len(tag):].lstrip()
    return None, msg


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


async def route_task_with_llm(user_message: str, llm=None) -> tuple[TaskType, str]:
    """Route with user-override > keywords > LLM fallback. Returns (type, cleaned_message)."""
    override, cleaned = _check_override(user_message)
    if override:
        return override, cleaned

    result = route_task(user_message)
    if result != TaskType.DIRECT or llm is None:
        return result, user_message

    # Keyword routing returned DIRECT (tie or zero hits) — ask LLM
    try:
        resp = await llm.chat([
            {"role": "system", "content": "Classify this task as exactly one of: BUGFIX, FEATURE, DIRECT. Reply with ONLY the word."},
            {"role": "user", "content": user_message[:500]},
        ])
        text = resp.text.strip().upper()
        if "BUG" in text:
            return TaskType.BUGFIX, user_message
        if "FEAT" in text:
            return TaskType.FEATURE, user_message
    except Exception:
        pass
    return TaskType.DIRECT, user_message

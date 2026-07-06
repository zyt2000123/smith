from __future__ import annotations

import re
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

# 上下文线索：消息中的结构性证据（stack trace / 错误日志 / 需求文档特征）。
# 比关键词更可信，每命中一条计 2 分（关键词 1 分）。
# 注意：不把异常类名（FooError/BarException）当线索——类名小写后必然命中
# "error"/"exception" 关键词，再计分就是同一证据算两遍，会把提到异常类的
# feature 请求误判成 bugfix。
_BUGFIX_CONTEXT = (
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r'File ".+", line \d+'),
    re.compile(r"\bat [\w.$<>]+\([\w.]+:\d+\)"),  # Java/JS 栈帧
    re.compile(r"(?i)(stack ?trace|error log|core ?dump|segmentation fault|segfault|堆栈|报错日志)"),
    re.compile(r"(?i)exit code [1-9]\d*"),
)

_FEATURE_CONTEXT = (
    re.compile(r"(?i)(user story|acceptance criteria|用户故事|验收标准|需求文档|PRD)"),
    re.compile(r"(?im)^as an? \w+.*i want"),
)

# Evaluation-Sensitive：检测评测/基准测试场景信号。词表刻意收窄，
# 避免"测试用例"等日常开发用语误报；误报的代价只是多一段谨慎提示。
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
    """检测消息是否处于评测敏感场景（QoderWake Evaluation-Sensitive Signal 的文本近似）。"""
    return bool(_EVAL_SENSITIVE.search(user_message))


def _check_override(msg: str) -> tuple[TaskType | None, str]:
    """If message starts with [bugfix]/[feature]/[direct], return that type and stripped message."""
    lower = msg.lstrip().lower()
    for tag, tt in [("[bugfix]", TaskType.BUGFIX), ("[feature]", TaskType.FEATURE), ("[direct]", TaskType.DIRECT)]:
        if lower.startswith(tag):
            return tt, msg.lstrip()[len(tag):].lstrip()
    return None, msg


def route_task(user_message: str) -> TaskType:
    """Classify a user message into a task type via keywords + context clues."""
    lower = user_message.lower()

    bug_score = sum(1 for kw in _BUGFIX_KEYWORDS if kw in lower)
    feat_score = sum(1 for kw in _FEATURE_KEYWORDS if kw in lower)
    bug_score += sum(2 for p in _BUGFIX_CONTEXT if p.search(user_message))
    feat_score += sum(2 for p in _FEATURE_CONTEXT if p.search(user_message))

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

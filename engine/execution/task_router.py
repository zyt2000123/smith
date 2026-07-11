"""Route a request through Smith's declarative identity catalog.

This module deliberately owns no domain taxonomy. Adding a legal, finance, or
other domain route is content work in ``agents/identities/*.yaml``, not a
Python edit here.
"""

from __future__ import annotations

import re

from engine.identity_catalog import IdentityCatalog, RouteDecision


# Evaluation-Sensitive：检测评测/基准测试场景信号。词表刻意收窄，避免“测试用例”等
# 日常开发用语误报；误报的代价只是多一段谨慎提示。
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


def route_task(
    user_message: str,
    catalog: IdentityCatalog,
    *,
    identity_id: str | None = None,
) -> RouteDecision:
    """Resolve one request against the loaded identity catalog."""
    return catalog.resolve(user_message, identity_id=identity_id)


async def route_task_with_llm(
    user_message: str,
    catalog: IdentityCatalog,
    llm=None,
    *,
    identity_id: str | None = None,
) -> RouteDecision:
    """Use deterministic catalog matches first, then optionally ask an LLM.

    The LLM is constrained to route ids already declared in the catalog; it
    cannot invent a new identity or pipeline name.
    """
    deterministic = route_task(user_message, catalog, identity_id=identity_id)
    if deterministic.score > 0 or llm is None or identity_id is not None:
        return deterministic

    choices = [
        f"{identity.id}:{route.id}"
        for identity in catalog.identities
        for route in identity.routes
    ]
    if not choices:
        return deterministic
    try:
        response = await llm.chat([
            {
                "role": "system",
                "content": (
                    "Choose exactly one declared route token, or DIRECT. "
                    f"Declared routes: {', '.join(choices)}"
                ),
            },
            {"role": "user", "content": user_message[:1000]},
        ])
        selected = response.text.strip()
        if selected.upper() == "DIRECT":
            return deterministic
        identity_key, route_key = selected.split(":", 1)
        identity = catalog.get(identity_key)
        for route in identity.routes:
            if route.id == route_key:
                return RouteDecision(identity, route.id, route.pipeline, score=1)
    except Exception:
        pass
    return deterministic

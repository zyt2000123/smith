from __future__ import annotations

import re
from typing import TYPE_CHECKING, AsyncGenerator

if TYPE_CHECKING:
    from engine.llm.client import LLMClient

DEFAULT_MAX_REACT_ITERS = 60
MAX_FAILED_TOOL_RECOVERY_ITERS = 20
MAX_PREFLIGHT_CHALLENGE_ITERS = 20
MAX_INCOMPLETE_FINAL_REPAIRS = 2
TOOL_FAILURE_HINT = (
    "Multiple tool calls have failed consecutively. Change your approach - "
    "try a different tool, simplify the command, or explain what you need without using tools."
)
INCOMPLETE_FINAL_AFTER_TOOL_HINT = (
    "Your last message described a next action instead of completing the user's request. "
    "Continue now: call the appropriate tool if more evidence is still needed, or provide "
    "a complete final answer. Do not only say what you will do next."
)
TOOL_FAILURE_BUDGET_MESSAGE = (
    "Tool failure recovery budget reached before a final answer."
)
PREFLIGHT_BUDGET_MESSAGE = (
    "Tool preflight challenge budget reached before an operation could run."
)
TOOL_CALL_BUDGET_MESSAGE = (
    "Tool-call budget reached before a final answer."
)

_NEXT_ACTION_VERBS = (
    "查",
    "搜",
    "抓",
    "获取",
    "打开",
    "访问",
    "确认",
    "验证",
    "看看",
    "看一下",
    "search",
    "fetch",
    "check",
    "open",
    "browse",
    "look up",
    "verify",
)
_INCOMPLETE_FINAL_PATTERNS = (
    re.compile(r"(让我|我将|我会|我需要|接下来|下一步|继续).{0,24}(" + "|".join(_NEXT_ACTION_VERBS[:8]) + r")"),
    re.compile(r"(let me|i'll|i will|i need to|next,?|going to).{0,48}(" + "|".join(_NEXT_ACTION_VERBS[8:]) + r")"),
)


def looks_like_incomplete_final_after_tool(text: str) -> bool:
    """Return true when a supposed final answer is only a promise to keep acting."""
    normalized = " ".join(text.strip().split()).lower()
    if not normalized or len(normalized) > 240:
        return False
    return any(pattern.search(normalized) for pattern in _INCOMPLETE_FINAL_PATTERNS)


def finalize_without_tools_prompt(reason: str) -> str:
    return (
        f"{reason}\n"
        "Do not call more tools. Give the user a concise final answer summarizing "
        "what was completed, what failed, and the next concrete step."
    )


def budget_exhausted_message(reason: str) -> str:
    return (
        f"{reason} I stopped to avoid an infinite loop. "
        "Please retry with a narrower request or inspect the latest failed tool result."
    )


async def final_text_response(
    llm: "LLMClient",
    conversation: list[dict],
    reason: str,
) -> str:
    fallback = budget_exhausted_message(reason)
    final_conversation = [
        *conversation,
        {"role": "system", "content": finalize_without_tools_prompt(reason)},
    ]
    try:
        response = await llm.chat(final_conversation, tools=None)
    except Exception:
        return fallback
    return response.text or fallback


async def stream_final_text(
    llm: "LLMClient",
    conversation: list[dict],
    reason: str,
) -> AsyncGenerator[str, None]:
    fallback = budget_exhausted_message(reason)
    final_conversation = [
        *conversation,
        {"role": "system", "content": finalize_without_tools_prompt(reason)},
    ]
    streamed_any = False
    try:
        async for chunk in llm.chat_stream(final_conversation):
            streamed_any = True
            yield chunk
    except Exception:
        pass
    if not streamed_any:
        yield fallback

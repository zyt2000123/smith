"""Context compression — prune old tool outputs + LLM-based compaction."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from engine.llm.contracts import DEFAULT_CONTEXT_WINDOW

if TYPE_CHECKING:
    from engine.llm.port import LLMPort

logger = logging.getLogger(__name__)

PRUNE_PROTECT_TURNS = 2
PRUNE_PROTECT_THRESHOLD_CHARS = 8000
PRUNE_MIN_CHARS = 2000
CONTEXT_TRIGGER_RATIO = 0.7
DEFAULT_CONTEXT_LIMIT = DEFAULT_CONTEXT_WINDOW
CONTEXT_DISPLAY_WINDOW = 256_000
CONTEXT_COMPACTION_TRIGGER = 128_000
DEFAULT_MAX_OUTPUT_TOKENS = 4_096
CONTEXT_SAFETY_MARGIN_RATIO = 0.10
CONTEXT_COMPACTION_INPUT_RATIO = 0.85

COMPACT_SYSTEM_PROMPT = """\
You are summarizing a conversation for an AI assistant that will lose all prior context.
This summary becomes the assistant's ONLY memory. Preserve every critical detail.

Output this exact XML structure:

<context_summary>
  <conversation_overview>
    <!-- One paragraph: user's goal, what was done, current state -->
  </conversation_overview>
  <key_knowledge>
    <!-- Bullet list: facts, conventions, constraints discovered -->
  </key_knowledge>
  <file_system_state>
    <!-- Files read/modified/created and what was learned -->
  </file_system_state>
  <recent_actions>
    <!-- Last few significant actions and outcomes -->
  </recent_actions>
  <current_plan>
    <!-- Step-by-step plan with [DONE]/[IN PROGRESS]/[TODO] markers -->
  </current_plan>
</context_summary>
"""

COMPACT_USER_PROMPT = (
    "Summarize our conversation above. Focus on what we did, what we're doing, "
    "which files we're working on, and what's next. Be dense with information."
)


def estimate_tokens(text: str) -> int:
    """粗略 token 估算。CJK 汉字约 1 字符/token，其余约 3 字符/token。

    旧版统一 len//3 对中文低估 2~3 倍，导致 compact 总在超出上下文窗口
    之后才触发。宁可略微高估提前压缩，也不要漏判把窗口撑爆。
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    return cjk + (len(text) - cjk) // 3


def prune_tool_outputs(
    conversation: list[dict],
    *,
    protect_turns: int = PRUNE_PROTECT_TURNS,
    protect_threshold: int = PRUNE_PROTECT_THRESHOLD_CHARS,
    min_prune: int = PRUNE_MIN_CHARS,
) -> int:
    """Remove old tool outputs in-place, protecting recent turns.

    Returns number of chars pruned.
    """
    turns = 0
    total_chars = 0
    pruned_chars = 0
    to_prune: list[dict] = []

    for i in range(len(conversation) - 1, -1, -1):
        msg = conversation[i]
        if msg.get("role") == "user":
            turns += 1
        if msg.get("role") == "tool":
            if turns < protect_turns:
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and "[pruned]" in content:
                break
            char_count = len(content) if isinstance(content, str) else 0
            total_chars += char_count
            if total_chars > protect_threshold:
                to_prune.append(msg)
                pruned_chars += char_count

    if pruned_chars < min_prune:
        return 0

    for msg in to_prune:
        msg["content"] = "[pruned]"

    return pruned_chars


def _conversation_tokens(conversation: list[dict]) -> int:
    return sum(
        estimate_tokens(m["content"])
        for m in conversation
        if isinstance(m.get("content"), str)
    )


def needs_compaction(
    conversation: list[dict],
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
    *,
    trigger_ratio: float = CONTEXT_TRIGGER_RATIO,
) -> bool:
    return _conversation_tokens(conversation) >= context_limit * trigger_ratio


def context_limit_for_llm(llm: object | None) -> int:
    """Use the selected route's declared model window with a safe fallback."""
    context_window = getattr(llm, "context_window", None)
    if isinstance(context_window, bool) or not isinstance(context_window, int) or context_window <= 0:
        return DEFAULT_CONTEXT_LIMIT
    return context_window


def compaction_policy_for_llm(llm: object | None) -> tuple[int, float]:
    """Return a safe input budget and the selected compaction trigger.

    The shell displays context against a stable 256k reference window. To
    keep the actual request from growing beyond the commonly supported 128k
    range, reserve room for output and provider/tool protocol overhead before
    deciding when to compact. A smaller declared window remains the hard
    safety limit for that route.
    """
    context_limit = min(context_limit_for_llm(llm), CONTEXT_COMPACTION_TRIGGER)
    configured_output = getattr(llm, "max_output_tokens", None)
    max_output_tokens = (
        configured_output
        if isinstance(configured_output, int)
        and not isinstance(configured_output, bool)
        and configured_output > 0
        else DEFAULT_MAX_OUTPUT_TOKENS
    )
    output_reserve = min(max_output_tokens, max(context_limit - 1, 1))
    safety_margin = min(
        max(256, int(context_limit * CONTEXT_SAFETY_MARGIN_RATIO)),
        max(context_limit - output_reserve - 1, 0),
    )
    input_budget = max(1, context_limit - output_reserve - safety_margin)
    return input_budget, CONTEXT_COMPACTION_INPUT_RATIO


def prompt_budget_for_llm(llm: object | None) -> int:
    """Limit static prompt assembly to leave room for conversation history."""
    input_budget, _ = compaction_policy_for_llm(llm)
    return max(1, int(input_budget * 0.6))


def trim_conversation_for_context_limit(
    conversation: list[dict],
    *,
    token_budget: int,
) -> list[dict]:
    """Deterministically shrink an over-limit conversation without another LLM call.

    This recovery path deliberately removes tool-call structure instead of
    retaining an orphaned assistant/tool pair. It is only used after a provider
    explicitly rejects context length, before any tool from the current model
    turn has been executed.
    """
    if token_budget <= 0 or _conversation_tokens(conversation) <= token_budget:
        return [dict(message) for message in conversation]

    system_text = ""
    for message in conversation:
        if message.get("role") == "system" and isinstance(message.get("content"), str):
            system_text = message["content"]
            break

    system_budget = int(token_budget * 0.55) if system_text else 0
    system_text = _trim_middle(system_text, system_budget) if system_text else ""
    history_budget = max(1, token_budget - estimate_tokens(system_text))

    history_lines: list[str] = []
    for message in conversation:
        role = str(message.get("role", "unknown"))
        if role == "system":
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content:
            tool_calls = message.get("tool_calls")
            if role == "assistant" and isinstance(tool_calls, list):
                names = ", ".join(
                    str(call.get("function", {}).get("name", "?"))
                    for call in tool_calls
                    if isinstance(call, dict)
                )
                content = f"[tool calls: {names}]" if names else ""
            else:
                content = ""
        if content:
            history_lines.append(f"[{role}] {content}")

    recovery_prefix = _trim_tail(
        "[Context deterministically shortened after provider context-limit error]\n",
        history_budget,
    )
    history_text = _trim_tail(
        "\n".join(history_lines),
        max(0, history_budget - estimate_tokens(recovery_prefix)),
    )
    result: list[dict] = []
    if system_text:
        result.append({"role": "system", "content": system_text})
    result.append({"role": "user", "content": recovery_prefix + history_text})
    return result


def _trim_middle(text: str, token_budget: int) -> str:
    if token_budget <= 0:
        return ""
    if estimate_tokens(text) <= token_budget:
        return text
    marker = "\n[... context truncated ...]\n"
    low, high = 0, len(text)
    best = ""
    while low <= high:
        keep = (low + high) // 2
        head = keep // 2
        tail = keep - head
        candidate = text[:head] + marker + (text[-tail:] if tail else "")
        if estimate_tokens(candidate) <= token_budget:
            best = candidate
            low = keep + 1
        else:
            high = keep - 1
    return best or _trim_tail(marker, token_budget)


def _trim_tail(text: str, token_budget: int) -> str:
    if token_budget <= 0:
        return ""
    if estimate_tokens(text) <= token_budget:
        return text
    marker = "[... earlier context truncated ...]\n"
    low, high = 0, len(text)
    best = ""
    while low <= high:
        keep = (low + high) // 2
        candidate = marker + (text[-keep:] if keep else "")
        if estimate_tokens(candidate) <= token_budget:
            best = candidate
            low = keep + 1
        else:
            high = keep - 1
    return best


async def compress(conversation: list[dict], llm: "LLMPort | None" = None) -> list[dict]:
    """Two-stage compression: prune first, compact if still over threshold.

    Returns the conversation list (mutated in-place for prune, replaced for compact).
    """
    prune_tool_outputs(conversation)
    if llm is not None:
        context_limit, trigger_ratio = compaction_policy_for_llm(llm)
        if needs_compaction(
            conversation,
            context_limit=context_limit,
            trigger_ratio=trigger_ratio,
        ):
            return await compact_history(conversation, llm)
    return conversation


async def compact_history(conversation: list[dict], llm: "LLMPort") -> list[dict]:
    """Replace conversation with a compacted summary via LLM.

    Returns a new conversation list: [system_prompt, summary_message].
    The original system prompt (first message) is preserved.
    """
    system_msg = conversation[0] if conversation and conversation[0].get("role") == "system" else None

    summary_messages = [
        {"role": "system", "content": COMPACT_SYSTEM_PROMPT},
    ]
    for msg in conversation:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            continue
        if role == "tool":
            # 工具结果是任务的关键证据，必须进摘要输入；
            # 旧版整体丢弃 tool 消息 → 工具密集任务压缩一次即失忆。
            if isinstance(content, str) and content:
                summary_messages.append({"role": "user", "content": f"[工具结果] {content[:1500]}"})
            continue
        if role == "assistant" and not content and msg.get("tool_calls"):
            # 带工具调用但无正文的 assistant 轮：记下调用了哪些工具。
            names = ", ".join(
                tc.get("function", {}).get("name", "?") for tc in msg["tool_calls"]
            )
            summary_messages.append({"role": "assistant", "content": f"[调用工具] {names}"})
            continue
        if role in ("user", "assistant") and content:
            summary_messages.append({"role": role, "content": content[:2000]})

    response = await llm.chat(summary_messages + [{"role": "user", "content": COMPACT_USER_PROMPT}])
    summary = (response.text or "").strip()
    finish_reason = getattr(response, "finish_reason", None)
    if not summary or finish_reason not in (None, "stop"):
        # 摘要为空/被截断/被拒答时整体替换历史等于静默失忆——
        # 放弃本轮 compact，保留 prune 后的原始对话。
        logger.warning(
            "compact_history discarded (finish_reason=%r, summary_chars=%d); keeping original conversation",
            finish_reason, len(summary),
        )
        return conversation

    result = []
    if system_msg:
        result.append(system_msg)
    result.append({"role": "user", "content": f"[Previous conversation summary]\n{summary}"})
    result.append({"role": "assistant", "content": "Understood. I have the full context from our previous conversation. How can I help?"})
    return result

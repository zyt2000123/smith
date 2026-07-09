"""Context compression — prune old tool outputs + LLM-based compaction."""

from __future__ import annotations

PRUNE_PROTECT_TURNS = 2
PRUNE_PROTECT_THRESHOLD_CHARS = 8000
PRUNE_MIN_CHARS = 2000
CONTEXT_TRIGGER_RATIO = 0.7
PROTECTED_TOOLS = frozenset({"read_file", "skill_load"})

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
    return len(text) // 3


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


def _total_chars(conversation: list[dict]) -> int:
    return sum(len(m.get("content", "")) for m in conversation if isinstance(m.get("content"), str))


def _estimate_tokens_from_chars(char_count: int) -> int:
    return max(char_count // 3, 1) if char_count > 0 else 0


def needs_compaction(conversation: list[dict], context_limit: int = 120000) -> bool:
    return _estimate_tokens_from_chars(_total_chars(conversation)) > context_limit * CONTEXT_TRIGGER_RATIO


async def compress(conversation: list[dict], llm: "LLMClient" = None) -> list[dict]:
    """Two-stage compression: prune first, compact if still over threshold.

    Returns the conversation list (mutated in-place for prune, replaced for compact).
    """
    prune_tool_outputs(conversation)
    if llm is not None and needs_compaction(conversation):
        return await compact_history(conversation, llm)
    return conversation


async def compact_history(conversation: list[dict], llm: "LLMClient") -> list[dict]:
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
        if role in ("user", "assistant") and content:
            summary_messages.append({"role": role, "content": content[:2000]})

    response = await llm.chat(summary_messages + [{"role": "user", "content": COMPACT_USER_PROMPT}])
    summary = response.text

    result = []
    if system_msg:
        result.append(system_msg)
    result.append({"role": "user", "content": f"[Previous conversation summary]\n{summary}"})
    result.append({"role": "assistant", "content": "Understood. I have the full context from our previous conversation. How can I help?"})
    return result

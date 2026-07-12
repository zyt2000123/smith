from __future__ import annotations

import asyncio
from types import SimpleNamespace

from engine.execution.compression import compact_history, needs_compaction


def test_needs_compaction_uses_actual_conversation_size() -> None:
    conversation = [{"role": "system", "content": "x" * 300_000}]

    assert needs_compaction(conversation, context_limit=120_000)


def test_needs_compaction_stays_false_for_small_conversations() -> None:
    conversation = [{"role": "user", "content": "hello"}]

    assert not needs_compaction(conversation, context_limit=120_000)


def test_needs_compaction_accounts_for_cjk_density() -> None:
    # 90k 中文字符 ≈ 90k tokens，超过 84k（120k×0.7）阈值。
    # 旧 len//3 估成 30k 会漏判 → compact 迟迟不触发，超窗口后才醒。
    conversation = [{"role": "user", "content": "证" * 90_000}]

    assert needs_compaction(conversation, context_limit=120_000)


def test_compact_history_keeps_tool_evidence_in_summary_input() -> None:
    # 压缩摘要的输入必须包含工具结果与工具调用意图，
    # 否则工具密集任务压缩一次就等于失忆。
    captured: dict = {}

    class FakeLLM:
        async def chat(self, messages, tools=None):
            captured["messages"] = messages
            return SimpleNamespace(text="summary")

    conversation = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "读取数据库配置"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "read_file"}}]},
        {"role": "tool", "content": "DATABASE_URL=postgres://demo"},
    ]

    asyncio.run(compact_history(conversation, FakeLLM()))

    blob = " ".join(m["content"] for m in captured["messages"])
    assert "DATABASE_URL" in blob   # 工具结果必须进摘要输入
    assert "read_file" in blob      # 工具调用意图也要保留


def test_compact_history_discards_empty_summary() -> None:
    # 摘要为空时整体替换历史 = 静默失忆；必须原样保留对话。
    class EmptyLLM:
        async def chat(self, messages, tools=None):
            return SimpleNamespace(text="   ")

    conversation = [
        {"role": "system", "content": "sp"},
        {"role": "user", "content": "hello"},
    ]
    result = asyncio.run(compact_history(conversation, EmptyLLM()))

    assert result is conversation


def test_compact_history_discards_truncated_summary() -> None:
    # finish_reason=length 说明摘要被截断，不能拿半句话当全部记忆。
    class TruncatedLLM:
        async def chat(self, messages, tools=None):
            return SimpleNamespace(text="partial summary", finish_reason="length")

    conversation = [{"role": "user", "content": "hi"}]
    result = asyncio.run(compact_history(conversation, TruncatedLLM()))

    assert result is conversation

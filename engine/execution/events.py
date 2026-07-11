"""Structured execution events for streaming progress to frontends.

Defines the event protocol used between the execution engine and the
server's SSE endpoint. Each event carries a type and a data payload
that the frontend can render incrementally.

Integration into agent_loop.py will come in a follow-up change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """All event types emitted during agent execution."""

    RUN_STARTED = "run_started"             # 一次 Agent run 已开始
    RAW_RESPONSE_EVENT = "raw_response_event"  # Provider 原始流事件（已规范化）
    THINKING = "thinking"                   # LLM 推理中（一轮 ReAct 决策开始）
    TEXT_DELTA = "text_delta"               # 增量文本输出
    TOOL_CALL_START = "tool_call_start"     # 工具执行开始
    TOOL_CALL_RESULT = "tool_call_result"   # 工具执行完成
    SKILL_START = "skill_start"             # 技能链节点开始
    SKILL_END = "skill_end"                 # 技能链节点完成
    GATE_RESULT = "gate_result"             # 门禁检查结果
    ROUTE_DECIDED = "route_decided"         # 任务路由决策
    BACKTRACK = "backtrack"                 # 回溯到更早的节点
    BLOCKED = "blocked"                     # 执行阻塞，需要人工介入
    TOKEN_USAGE = "token_usage"             # LLM token 使用量
    PROVISIONAL_TEXT_DELTA = "provisional_text_delta"  # 技能链内未过门禁的草稿文本
    PROVISIONAL_COMMIT = "provisional_commit"        # 门禁通过，草稿转正
    PROVISIONAL_RETRACT = "provisional_retract"      # 门禁失败，撤回草稿
    INCOMPLETE = "incomplete"               # 因预算或模型输出限制而未完成
    FAILED = "failed"                       # 执行异常，未能正常完成
    DONE = "done"                           # 执行完成
    RUN_FINISHED = "run_finished"           # 所有后处理完成后的 run 终态


@dataclass
class ExecutionEvent:
    """A single event emitted during agent execution.

    Attributes:
        type: The event type.
        data: Arbitrary payload — structure depends on the event type.
    """

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        """Format as a Server-Sent Events message."""
        return f"event: {self.type.value}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON transport."""
        return {"type": self.type.value, "data": self.data}

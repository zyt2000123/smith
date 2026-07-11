"""Pipeline executor — walks a SkillChain node-by-node with ReAct + gates.

Extracted from agent_loop.py so pipeline execution logic is isolated from
routing, lifecycle management, and legacy compatibility.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator

from .backtrack import FailureLoopGuard, FailureSignature
from .events import EventType, ExecutionEvent
from .gate import LLMGate, SkillRubricGate
from .react_loop import react_event_loop

if TYPE_CHECKING:
    from engine.llm.client import LLMClient
    from engine.safety.tool_guard import ToolGuard
    from engine.skill.registry import SkillRegistry
    from engine.tool.registry import ToolRegistry
    from .skill_chain import SkillChain

logger = logging.getLogger(__name__)

_rubric_gate = SkillRubricGate()
_RUBRIC_MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Public: pipeline runner
# ---------------------------------------------------------------------------


async def run_pipeline(
    chain: "SkillChain",
    llm: "LLMClient",
    user_message: str,
    base_messages: list[dict],
    tool_registry: "ToolRegistry",
    skill_registry: "SkillRegistry",
    tool_guard: "ToolGuard | None",
    guard: FailureLoopGuard,
    max_react_iters: int,
    context: dict,
) -> AsyncGenerator[ExecutionEvent, None]:
    """Execute a pipeline: walk nodes sequentially, ReAct each, gate-check."""
    from engine.skill.executor import execute_skill_events

    node_idx = 0
    max_backtracks = 5
    backtrack_count = 0

    while node_idx < len(chain.nodes):
        node = chain.nodes[node_idx]

        if node.condition is not None and not node.condition(context):
            node_idx += 1
            continue

        yield ExecutionEvent(EventType.SKILL_START, {"skill": node.skill_name, "index": node_idx})

        rubric_attempt = 0
        output = ""
        rubric_passed = False
        provision_id = ""

        while rubric_attempt < _RUBRIC_MAX_RETRIES:
            provision_id = f"{node.skill_name}:{node_idx}:{rubric_attempt}"
            skill = skill_registry.get(node.skill_name)

            if skill is None:
                messages = base_messages + [{"role": "user", "content": f"[Skill: {node.skill_name}] {user_message}"}]
                if rubric_attempt == 1 and context.get("_rubric_retry_hint"):
                    messages.append({"role": "user", "content": context["_rubric_retry_hint"]})
                elif rubric_attempt == 2:
                    messages.append({"role": "user", "content": "Switch strategy: try a completely different approach."})
                event_stream = react_event_loop(
                    llm, messages, tool_registry, tool_guard, max_react_iters,
                )
            else:
                skill_context = dict(context)
                if rubric_attempt == 1 and skill_context.get("_rubric_retry_hint"):
                    skill_context["rubric_feedback"] = skill_context["_rubric_retry_hint"]
                elif rubric_attempt == 2:
                    skill_context["rubric_feedback"] = "Switch strategy: try a completely different approach."
                messages = [{"role": "user", "content": user_message}]
                event_stream = execute_skill_events(
                    skill, llm, tool_registry, messages, skill_context,
                    max_react_iters, tool_guard=tool_guard,
                )

            result = _NodeResult()
            async for event in _collect_node_events(event_stream, provision_id):
                if isinstance(event, _NodeResult):
                    result = event
                else:
                    yield event

            if result.incomplete_reason:
                if result.text:
                    data: dict[str, object] = {"text": result.text}
                    if result.was_streamed:
                        data["already_streamed"] = True
                    yield ExecutionEvent(EventType.TEXT_DELTA, data)
                yield ExecutionEvent(EventType.DONE, {})
                return
            output = result.text

            rubric_result = await _rubric_gate.check(output, context)
            if rubric_result.verdict == "pass":
                rubric_passed = True
                break
            context["_rubric_retry_hint"] = rubric_result.retry_hint or ""
            rubric_attempt += 1

        context.pop("_rubric_retry_hint", None)

        if not rubric_passed:
            yield ExecutionEvent(EventType.PROVISIONAL_RETRACT, {
                "provision_id": provision_id, "reason": rubric_result.reason,
            })
            yield ExecutionEvent(EventType.BLOCKED, {"skill": node.skill_name, "reason": rubric_result.reason})
            yield ExecutionEvent(EventType.DONE, {})
            return

        if isinstance(node.gate, LLMGate):
            node.gate.set_llm(llm)
        gate_result = await node.gate.check(output, context)
        yield ExecutionEvent(EventType.GATE_RESULT, {
            "skill": node.skill_name, "verdict": gate_result.verdict, "reason": gate_result.reason,
        })

        if gate_result.verdict == "pass":
            yield ExecutionEvent(EventType.PROVISIONAL_COMMIT, {"provision_id": provision_id})
            context[f"{node.skill_name}_output"] = output
            context[f"_{node.skill_name}_output_was_streamed"] = result.was_streamed
            _save_checkpoint(context, node_idx)
            yield ExecutionEvent(EventType.SKILL_END, {"skill": node.skill_name, "status": "passed"})
            node_idx += 1
            continue

        sig = FailureSignature(error_type=node.skill_name, context_hash=hashlib.md5(output.encode()).hexdigest()[:8])
        action = guard.record(sig)

        yield ExecutionEvent(EventType.PROVISIONAL_RETRACT, {
            "provision_id": provision_id, "reason": gate_result.reason,
        })

        if action == "blocked":
            yield ExecutionEvent(EventType.BLOCKED, {"skill": node.skill_name, "reason": gate_result.reason})
            yield ExecutionEvent(EventType.DONE, {})
            return

        if action == "switch" and node.skill_name in chain.backtrack_map:
            backtrack_count += 1
            if backtrack_count > max_backtracks:
                yield ExecutionEvent(EventType.BLOCKED, {"skill": node.skill_name, "reason": "max backtracks"})
                yield ExecutionEvent(EventType.DONE, {})
                return
            target = chain.backtrack_map[node.skill_name]
            yield ExecutionEvent(EventType.BACKTRACK, {"from": node.skill_name, "to": target})
            node_idx = next((i for i, n in enumerate(chain.nodes) if n.skill_name == target), 0)
            continue

        yield ExecutionEvent(EventType.SKILL_END, {"skill": node.skill_name, "status": "retry"})

    # Emit final output
    for node in reversed(chain.nodes):
        key = f"{node.skill_name}_output"
        if key in context:
            data: dict[str, object] = {"text": context[key]}
            if context.get(f"_{node.skill_name}_output_was_streamed"):
                data["already_streamed"] = True
            yield ExecutionEvent(EventType.TEXT_DELTA, data)
            break

    _clear_checkpoint(context)
    yield ExecutionEvent(EventType.DONE, {})


# ---------------------------------------------------------------------------
# Internal: event collection (eliminates the 3x copy-paste)
# ---------------------------------------------------------------------------


class _NodeResult:
    __slots__ = ("text", "was_streamed", "incomplete_reason")

    def __init__(self) -> None:
        self.text = ""
        self.was_streamed = False
        self.incomplete_reason: str | None = None


async def _collect_node_events(
    event_stream: AsyncGenerator[ExecutionEvent, None],
    provision_id: str,
) -> AsyncGenerator[ExecutionEvent | _NodeResult, None]:
    """Collect TEXT_DELTA into result, convert RAW to PROVISIONAL, forward the rest.

    Yields ExecutionEvents to forward, then a final _NodeResult with collected text.
    """
    parts: list[str] = []
    was_streamed = False
    incomplete_reason: str | None = None

    async for event in event_stream:
        if event.type == EventType.TEXT_DELTA:
            parts.append(str(event.data.get("text", "")))
            was_streamed = was_streamed or bool(event.data.get("already_streamed"))
            continue
        elif event.type == EventType.RAW_RESPONSE_EVENT:
            raw_type = event.data.get("type")
            raw_data = event.data.get("data")
            if raw_type == "response.output_text.delta" and isinstance(raw_data, dict):
                delta = raw_data.get("delta")
                if isinstance(delta, str) and delta:
                    yield ExecutionEvent(EventType.PROVISIONAL_TEXT_DELTA, {
                        "text": delta, "provision_id": provision_id,
                    })
            continue
        elif event.type == EventType.INCOMPLETE:
            incomplete_reason = str(event.data.get("reason", "agent_incomplete"))
        yield event

    result = _NodeResult()
    result.text = "".join(parts)
    result.was_streamed = was_streamed
    result.incomplete_reason = incomplete_reason
    yield result


# ---------------------------------------------------------------------------
# Internal: checkpoint helpers
# ---------------------------------------------------------------------------


def _save_checkpoint(context: dict, node_idx: int) -> None:
    session_id = str(context.get("session_id") or "")
    profile_dir = str(context.get("_profile_dir") or "")
    if not session_id or not profile_dir:
        return
    try:
        from .session_state import SessionStateManager, SessionCheckpoint
        SessionStateManager(Path(profile_dir)).save(SessionCheckpoint(
            agent_id=str(context.get("agent_id") or ""),
            session_id=session_id,
            task_type=str(context.get("task_type") or ""),
            skill_chain_index=node_idx,
            context={k: v for k, v in context.items() if not k.startswith("_")},
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
    except Exception:
        logger.exception("failed to save session checkpoint")


def _clear_checkpoint(context: dict) -> None:
    session_id = str(context.get("session_id") or "")
    profile_dir = str(context.get("_profile_dir") or "")
    if not session_id or not profile_dir:
        return
    try:
        from .session_state import SessionStateManager
        SessionStateManager(Path(profile_dir)).clear(session_id)
    except Exception:
        logger.exception("failed to clear session checkpoint")

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
from uuid import uuid4

from .backtrack import FailureLoopGuard, FailureSignature
from .events import EventType, ExecutionEvent
from .gate import LLMGate, SkillRubricGate
from .react_loop import react_event_loop

if TYPE_CHECKING:
    from engine.llm.port import LLMPort
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
    llm: "LLMPort",
    user_message: str,
    base_messages: list[dict],
    tool_registry: "ToolRegistry",
    skill_registry: "SkillRegistry",
    tool_guard: "ToolGuard | None",
    guard: FailureLoopGuard,
    max_react_iters: int,
    context: dict,
    gate_llm: "LLMPort | None" = None,
) -> AsyncGenerator[ExecutionEvent, None]:
    """Execute a pipeline: walk nodes sequentially, ReAct each, gate-check."""
    from engine.skill.executor import execute_skill_events

    node_idx = 0
    max_backtracks = 5
    backtrack_count = 0
    committed_provisional_output: dict[str, bool] = {}

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
        provision_settled = True

        try:
            while rubric_attempt < _RUBRIC_MAX_RETRIES:
                provision_id = f"{node.skill_name}:{node_idx}:{rubric_attempt}:{uuid4().hex}"
                provision_settled = False
                skill = skill_registry.get(node.skill_name)

                if skill is None:
                    messages = base_messages + [{"role": "user", "content": f"[Skill: {node.skill_name}] {user_message}"}]
                    if rubric_attempt == 1 and context.get("_rubric_retry_hint"):
                        messages.append({"role": "user", "content": context["_rubric_retry_hint"]})
                    elif rubric_attempt == 2:
                        messages.append({"role": "user", "content": "Switch strategy: try a completely different approach."})
                    event_stream = react_event_loop(
                        llm, messages, tool_registry, tool_guard, max_react_iters,
                        provisional_lifecycle=False,
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
                        max_react_iters, tool_guard=tool_guard, provisional_lifecycle=False,
                    )

                result = _NodeResult()
                async for event in _collect_node_events(event_stream, provision_id):
                    if isinstance(event, _NodeResult):
                        result = event
                    else:
                        yield event

                if result.incomplete_reason or result.failed_reason:
                    reason = result.failed_reason or result.incomplete_reason
                    yield ExecutionEvent(EventType.PROVISIONAL_RETRACT, {
                        "provision_id": provision_id, "reason": reason,
                    })
                    provision_settled = True
                    if result.text:
                        yield ExecutionEvent(EventType.TEXT_DELTA, {"text": result.text})
                    yield ExecutionEvent(EventType.DONE, {})
                    return
                output = result.text

                rubric_result = await _rubric_gate.check(output, context)
                if rubric_result.verdict == "pass":
                    rubric_passed = True
                    break
                context["_rubric_retry_hint"] = rubric_result.retry_hint or ""
                yield ExecutionEvent(EventType.PROVISIONAL_RETRACT, {
                    "provision_id": provision_id, "reason": "rubric_retry",
                })
                provision_settled = True
                rubric_attempt += 1

            context.pop("_rubric_retry_hint", None)

            if not rubric_passed:
                yield ExecutionEvent(EventType.BLOCKED, {"skill": node.skill_name, "reason": rubric_result.reason})
                yield ExecutionEvent(EventType.DONE, {})
                return

            if isinstance(node.gate, LLMGate):
                node.gate.set_llm(gate_llm or llm)
            gate_result = await node.gate.check(output, context)
            yield ExecutionEvent(EventType.GATE_RESULT, {
                "skill": node.skill_name, "verdict": gate_result.verdict, "reason": gate_result.reason,
            })

            if gate_result.verdict == "pass":
                yield ExecutionEvent(EventType.PROVISIONAL_COMMIT, {"provision_id": provision_id})
                provision_settled = True
                context[f"{node.skill_name}_output"] = output
                committed_provisional_output[node.skill_name] = result.was_provisional
                _save_checkpoint(context, node_idx)
                yield ExecutionEvent(EventType.SKILL_END, {"skill": node.skill_name, "status": "passed"})
                node_idx += 1
                continue

            sig = FailureSignature(error_type=node.skill_name, context_hash=hashlib.md5(output.encode()).hexdigest()[:8])
            action = guard.record(sig)

            yield ExecutionEvent(EventType.PROVISIONAL_RETRACT, {
                "provision_id": provision_id, "reason": gate_result.reason,
            })
            provision_settled = True

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
        except Exception:
            if not provision_settled:
                yield ExecutionEvent(EventType.PROVISIONAL_RETRACT, {
                    "provision_id": provision_id, "reason": "execution_error",
                })
            raise

    # Provisional events now reach the session UI.  The final semantic text is
    # still emitted for persistence, but consumers that rendered the accepted
    # provisional text must not append it again.
    for node in reversed(chain.nodes):
        key = f"{node.skill_name}_output"
        if key in context:
            data: dict[str, object] = {"text": context[key]}
            if committed_provisional_output.get(node.skill_name):
                data["already_streamed"] = True
            yield ExecutionEvent(EventType.TEXT_DELTA, data)
            break

    _clear_checkpoint(context)
    yield ExecutionEvent(EventType.DONE, {})


# ---------------------------------------------------------------------------
# Internal: event collection (eliminates the 3x copy-paste)
# ---------------------------------------------------------------------------


class _NodeResult:
    __slots__ = ("text", "was_provisional", "incomplete_reason", "failed_reason")

    def __init__(self) -> None:
        self.text = ""
        self.was_provisional = False
        self.incomplete_reason: str | None = None
        self.failed_reason: str | None = None


async def _collect_node_events(
    event_stream: AsyncGenerator[ExecutionEvent, None],
    provision_id: str,
) -> AsyncGenerator[ExecutionEvent | _NodeResult, None]:
    """Collect TEXT_DELTA into result, convert RAW to PROVISIONAL, forward the rest.

    Yields ExecutionEvents to forward, then a final _NodeResult with collected text.
    """
    parts: list[str] = []
    was_provisional = False
    incomplete_reason: str | None = None
    failed_reason: str | None = None

    async for event in event_stream:
        if event.type == EventType.TEXT_DELTA:
            parts.append(str(event.data.get("text", "")))
            continue
        elif event.type == EventType.RAW_RESPONSE_EVENT:
            raw_type = event.data.get("type")
            raw_data = event.data.get("data")
            if raw_type == "response.output_text.delta" and isinstance(raw_data, dict):
                delta = raw_data.get("delta")
                if isinstance(delta, str) and delta:
                    was_provisional = True
                    yield ExecutionEvent(EventType.PROVISIONAL_TEXT_DELTA, {
                        "text": delta, "provision_id": provision_id,
                    })
            continue
        elif event.type == EventType.INCOMPLETE:
            incomplete_reason = str(event.data.get("reason", "agent_incomplete"))
        elif event.type == EventType.FAILED:
            failed_reason = str(event.data.get("reason", "agent_failed"))
        yield event

    result = _NodeResult()
    result.text = "".join(parts)
    result.was_provisional = was_provisional
    result.incomplete_reason = incomplete_reason
    result.failed_reason = failed_reason
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

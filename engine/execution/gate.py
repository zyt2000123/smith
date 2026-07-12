"""Gate framework for pipeline quality checks.

The engine owns only the *mechanism*: the ``Gate`` protocol, the
``GateResult`` contract, and the ``LLMGate`` wrapper that layers LLM
semantic verification over a cheap heuristic pre-filter.

Concrete gate implementations are content, not engine code.  They live
under ``agents/gates/<domain>/`` and are registered at startup by
``engine.execution.skill_chain.load_gate_content``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Protocol

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    verdict: Literal["pass", "fail", "retry"]
    reason: str
    retry_hint: str | None = None


class Gate(Protocol):
    async def check(self, output: str, context: dict) -> GateResult: ...


class LLMGate:
    """LLM-based semantic verification layer on top of a heuristic pre-filter."""

    def __init__(self, inner: Gate, prompt_template: str):
        self._inner = inner
        self._prompt_template = prompt_template
        self._llm = None  # set via set_llm()

    def set_llm(self, llm):
        self._llm = llm

    async def check(self, output: str, context: dict) -> GateResult:
        # First run the heuristic pre-filter
        result = await self._inner.check(output, context)
        if result.verdict == "fail":
            return result  # pre-filter already caught it, no need for LLM

        # Pre-filter passed — now verify semantically with LLM
        if not self._llm:
            return result  # no LLM available, trust the pre-filter

        try:
            prompt = self._prompt_template.format(output=output[:2000])
            resp = await self._llm.chat([
                {"role": "system", "content": "You are a quality gate. Evaluate the output and respond with ONLY 'PASS' or 'FAIL: <reason>'. Be strict."},
                {"role": "user", "content": prompt},
            ])
            text = resp.text.strip()
            if text.startswith("FAIL"):
                reason = text[5:].strip(": ")
                return GateResult("fail", f"LLM verification: {reason}", retry_hint=reason)
        except Exception:
            # fail-open 是刻意选择（gate LLM 挂了不阻塞主流程），
            # 但退化必须留痕，否则语义校验静默失效永远无人发现。
            logger.warning(
                "gate LLM verification failed; falling back to pre-filter verdict",
                exc_info=True,
            )

        return result

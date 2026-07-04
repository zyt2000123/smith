from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class GateResult:
    verdict: Literal["pass", "fail", "retry"]
    reason: str
    retry_hint: str | None = None


class Gate(Protocol):
    async def check(self, output: str, context: dict) -> GateResult: ...


class PlanningGate:
    """Check that output has numbered steps (>= 3) and verification points."""

    async def check(self, output: str, context: dict) -> GateResult:
        # Count numbered steps: "1." or "1、" at line start (with optional whitespace)
        steps = re.findall(r"^\s*\d+[.、)]\s", output, re.MULTILINE)
        num_steps = len(steps)

        has_verify = bool(re.search(
            r"验证|检查|确认|verify|check|test",
            output,
            re.IGNORECASE,
        ))

        if num_steps >= 3 and has_verify:
            return GateResult("pass", f"Plan has {num_steps} numbered steps and verification points.")

        missing = []
        if num_steps < 3:
            missing.append(f"at least 3 numbered steps (found {num_steps})")
        if not has_verify:
            missing.append("verification points")
        return GateResult(
            "retry",
            f"Planning output missing: {', '.join(missing)}.",
            retry_hint="Add a verification checkpoint after each step (e.g., '验证: 运行测试确认...'). Ensure at least 3 numbered steps.",
        )


class TestGate:
    """Check that output has >= 2 test case descriptions and edge case coverage."""

    async def check(self, output: str, context: dict) -> GateResult:
        # Count distinct test mentions
        test_patterns = re.findall(
            r"测试用例|test\s*case|should\s|expect\s|assert|it\s*\(",
            output,
            re.IGNORECASE,
        )
        num_tests = len(test_patterns)

        has_edge = bool(re.search(
            r"边界|异常|edge|boundary|error|corner|negative",
            output,
            re.IGNORECASE,
        ))

        if num_tests >= 2 and has_edge:
            return GateResult("pass", f"Output includes {num_tests} test cases with edge case coverage.")

        missing = []
        if num_tests < 2:
            missing.append(f"at least 2 test case descriptions (found {num_tests})")
        if not has_edge:
            missing.append("edge case / boundary / error coverage")
        return GateResult(
            "retry",
            f"Testing output missing: {', '.join(missing)}.",
            retry_hint="Include at least 2 concrete test cases with expected behavior, and cover edge cases (boundary conditions, error paths).",
        )


class ValidationGate:
    """Check for evidence of actual execution and pass/fail results."""

    async def check(self, output: str, context: dict) -> GateResult:
        has_execution = bool(re.search(
            r"运行|执行|ran\b|executed|output|结果|stdout|stderr|\$\s",
            output,
            re.IGNORECASE,
        ))

        # Pass/fail with specifics — not just the bare word "passed"
        has_results = bool(re.search(
            r"(\d+\s*(passed|failed|tests?))|"
            r"(pass(?:ed)?.*\d)|(fail(?:ed)?.*\d)|"
            r"(✓|✗|PASS|FAIL)|"
            r"(通过\s*\d)|(失败\s*\d)|"
            r"(test.*result)|"
            r"(assert.*(?:true|false|equal))",
            output,
            re.IGNORECASE,
        ))

        if has_execution and has_results:
            return GateResult("pass", "Validation shows execution evidence and pass/fail results.")

        missing = []
        if not has_execution:
            missing.append("evidence of actual execution (e.g., command output, logs)")
        if not has_results:
            missing.append("specific pass/fail results (not just the word 'passed')")
        return GateResult(
            "retry",
            f"Validation output missing: {', '.join(missing)}.",
            retry_hint="Run the tests/commands and include the actual output showing pass/fail counts or specific results.",
        )


class ReviewGate:
    """Check for issue categorization and actionable findings."""

    async def check(self, output: str, context: dict) -> GateResult:
        has_categorization = bool(re.search(
            r"P0|P1|P2|critical|major|minor|severity|"
            r"严重|主要|次要|优先级",
            output,
            re.IGNORECASE,
        ))

        has_finding = bool(re.search(
            r"(issue|finding|problem|bug|concern|建议|问题|发现)",
            output,
            re.IGNORECASE,
        ))

        has_no_issues = bool(re.search(
            r"no\s*(issues?|problems?|findings?)\s*found|"
            r"(looks?\s*good|LGTM|approved)|"
            r"没有(发现)?(问题|缺陷)",
            output,
            re.IGNORECASE,
        ))

        if has_categorization and (has_finding or has_no_issues):
            return GateResult("pass", "Review includes categorized findings or explicit clean bill.")

        missing = []
        if not has_categorization:
            missing.append("issue categorization (P0/P1/P2 or critical/major/minor)")
        if not has_finding and not has_no_issues:
            missing.append("at least one actionable finding OR explicit 'no issues found'")
        return GateResult(
            "retry",
            f"Review output missing: {', '.join(missing)}.",
            retry_hint="Categorize each finding by severity (P0/P1/P2 or critical/major/minor). If no issues, explicitly state 'no issues found'.",
        )


class RootCauseGate:
    """Check for evidence-backed root cause analysis."""

    async def check(self, output: str, context: dict) -> GateResult:
        has_cause = bool(re.search(
            r"根因|root\s*cause|原因是|caused\s*by|根本原因",
            output,
            re.IGNORECASE,
        ))

        has_evidence = bool(re.search(
            r"证据|evidence|因为|because|日志|log|stack|trace|"
            r"堆栈|输出|显示|表明",
            output,
            re.IGNORECASE,
        ))

        if has_cause and has_evidence:
            return GateResult("pass", "Root cause with supporting evidence found.")

        missing = []
        if not has_cause:
            missing.append("root cause statement (e.g., '根因: ...' or 'Root cause: ...')")
        if not has_evidence:
            missing.append("supporting evidence (logs, stack traces, or behavioral observation)")
        return GateResult(
            "retry",
            f"Root cause analysis missing: {', '.join(missing)}.",
            retry_hint="State the root cause explicitly and cite evidence (logs, stack traces, output, or behavioral observation).",
        )


class SkillRubricGate:
    """Generic quality check: output must be non-trivial and structured."""

    async def check(self, output: str, context: dict) -> GateResult:
        stripped = output.strip()

        if len(stripped) < 100:
            return GateResult(
                "retry",
                f"Output too short ({len(stripped)} chars, minimum 100).",
                retry_hint="Provide a more detailed response (at least 100 characters).",
            )

        has_structure = bool(re.search(
            r"^#{1,3}\s|"           # Markdown headers
            r"^\s*\d+[.、)]\s|"     # Numbered lists
            r"```",                 # Code blocks
            stripped,
            re.MULTILINE,
        ))

        if not has_structure:
            return GateResult(
                "retry",
                "Output lacks structured content (no headers, numbered lists, or code blocks).",
                retry_hint="Organize the response with headers (## Section), numbered steps, or code blocks for clarity.",
            )

        return GateResult("pass", "Output meets quality bar (length and structure).")

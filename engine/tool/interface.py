from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ToolSideEffect = Literal["none", "write", "external", "destructive"]
ToolConcurrency = Literal["safe", "serial"]
ToolExecutionEnvironment = Literal["host", "sandbox", "either"]
ToolApprovalPolicy = Literal["never", "policy", "always"]


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    # Security metadata — when declared, safety modules use these instead of
    # hardcoded lookup tables.  Tools that don't declare metadata still work
    # via the fallback tables in tool_guard / fact_gate.
    path_args: tuple[str, ...] = ()
    list_path_args: tuple[str, ...] = ()
    is_write_tool: bool = False
    permission_level: str = ""
    approval_policy: ToolApprovalPolicy = "never"
    read_actions: frozenset[str] = field(default_factory=frozenset)
    # Rich execution contract. Legacy providers keep the safe defaults.
    timeout_seconds: float | None = None
    retryable: bool = False
    side_effect: ToolSideEffect = "none"
    idempotent: bool = False
    concurrency: ToolConcurrency = "safe"
    execution_environment: ToolExecutionEnvironment = "host"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict = field(default_factory=dict)
    idempotency_key: str | None = None


@dataclass
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False
    error_kind: str | None = None
    retryable: bool = False
    timed_out: bool = False
    side_effect_status: Literal["none", "completed", "unknown"] = "none"
    metadata: dict[str, object] = field(default_factory=dict)

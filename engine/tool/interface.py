from __future__ import annotations

from dataclasses import dataclass, field


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
    read_actions: frozenset[str] = field(default_factory=frozenset)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False

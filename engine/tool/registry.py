from __future__ import annotations

import importlib.util
import traceback
from pathlib import Path
from typing import Any, Callable

from .interface import ToolCall, ToolDefinition, ToolResult
from .schema import function_to_schema
from .truncation import truncate_output


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolDefinition, Callable]] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable,
    ) -> None:
        defn = ToolDefinition(name=name, description=description, parameters=parameters)
        self._tools[name] = (defn, func)

    def load_providers(self, tools_dir: Path) -> None:
        """Auto-discover tool providers from a directory of .py files.

        Each file should define a TOOL_META dict and an execute function.
        TOOL_META keys: name, description, parameters (JSON Schema dict).
        """
        if not tools_dir.is_dir():
            return
        for py_file in sorted(tools_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                meta: dict[str, Any] = getattr(mod, "TOOL_META", {})
                execute_fn: Callable | None = getattr(mod, "execute", None)
                if meta and execute_fn:
                    self.register(
                        name=meta["name"],
                        description=meta.get("description", ""),
                        parameters=meta.get("parameters", {}),
                        func=execute_fn,
                    )
            except Exception:
                traceback.print_exc()

    def get_schemas(self, enabled: list[str] | None = None) -> list[dict]:
        """Return OpenAI-compatible tool schemas."""
        result: list[dict] = []
        for name, (defn, _) in self._tools.items():
            if enabled is not None and name not in enabled:
                continue
            result.append({
                "type": "function",
                "function": {
                    "name": defn.name,
                    "description": defn.description,
                    "parameters": defn.parameters,
                },
            })
        return result

    async def execute(self, call: ToolCall) -> ToolResult:
        entry = self._tools.get(call.name)
        if entry is None:
            return ToolResult(call_id=call.id, content=f"Unknown tool: {call.name}", is_error=True)

        _, func = entry
        try:
            import asyncio
            if asyncio.iscoroutinefunction(func):
                content = await func(**call.arguments)
            else:
                content = func(**call.arguments)
            result = ToolResult(call_id=call.id, content=str(content))
        except Exception as exc:
            result = ToolResult(call_id=call.id, content=str(exc), is_error=True)

        result = ToolResult(
            call_id=result.call_id,
            content=truncate_output(result.content, tool_name=call.name),
            is_error=result.is_error,
        )
        return result

    def list_tools(self) -> list[ToolDefinition]:
        return [defn for defn, _ in self._tools.values()]

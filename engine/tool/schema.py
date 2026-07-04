from __future__ import annotations

import inspect
import typing
from typing import Any, Callable, get_type_hints

_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _python_type_to_json(tp: Any) -> dict:
    """Convert a Python type annotation to a JSON Schema fragment."""
    origin = getattr(tp, "__origin__", None)

    # Optional[X] -> nullable X
    if origin is typing.Union:
        args = [a for a in tp.__args__ if a is not type(None)]
        if len(args) == 1:
            return _python_type_to_json(args[0])

    # list[X]
    if origin is list:
        item_type = tp.__args__[0] if tp.__args__ else str
        return {"type": "array", "items": _python_type_to_json(item_type)}

    if tp in _TYPE_MAP:
        return {"type": _TYPE_MAP[tp]}

    return {"type": "string"}


def function_to_schema(func: Callable) -> dict:
    """Inspect a Python function and produce an OpenAI-compatible JSON Schema.

    Uses type hints for parameter types and the docstring for description.
    """
    sig = inspect.signature(func)
    hints = get_type_hints(func)

    properties: dict[str, dict] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        tp = hints.get(name, str)
        schema = _python_type_to_json(tp)
        properties[name] = schema

        # Not required if has a default or is Optional
        origin = getattr(tp, "__origin__", None)
        is_optional = origin is typing.Union and type(None) in tp.__args__
        if param.default is inspect.Parameter.empty and not is_optional:
            required.append(name)

    description = inspect.getdoc(func) or ""

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }

from __future__ import annotations

import inspect
import types
import typing
from typing import Any, Callable, get_args, get_origin, get_type_hints

_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _python_type_to_json(tp: Any) -> dict:
    """Convert a Python type annotation to a JSON Schema fragment."""
    if tp is Any:
        return {}

    origin = get_origin(tp)
    args = get_args(tp)

    # Optional[X] -> nullable X
    if origin in (typing.Union, types.UnionType):
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            return _python_type_to_json(non_none_args[0])
        return {"anyOf": [_python_type_to_json(arg) for arg in non_none_args]}

    # list[X]
    if origin is list:
        item_type = args[0] if args else str
        return {"type": "array", "items": _python_type_to_json(item_type)}

    if origin is dict:
        value_type = args[1] if len(args) == 2 else Any
        return {"type": "object", "additionalProperties": _python_type_to_json(value_type)}

    if origin is typing.Literal:
        values = list(args)
        schema: dict[str, Any] = {"enum": values}
        if values:
            value_types = {type(value) for value in values}
            if len(value_types) == 1 and next(iter(value_types)) in _TYPE_MAP:
                schema["type"] = _TYPE_MAP[next(iter(value_types))]
        return schema

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
        if param.default is inspect.Parameter.empty and not _is_optional_type(tp):
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


def _is_optional_type(tp: Any) -> bool:
    origin = get_origin(tp)
    return origin in (typing.Union, types.UnionType) and type(None) in get_args(tp)

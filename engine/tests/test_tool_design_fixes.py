from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import tempfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tool.interface import ToolCall  # noqa: E402
from tool.registry import ToolRegistry  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]


def _load_tool_module(name: str):
    path = ROOT / "agents" / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_text_error_results_are_marked_as_errors():
    async def fail_with_text():
        return "Error: no such file"

    async def fail_with_exit_code():
        return "[exit_code=2]\nfailed"

    async def ok():
        return "OK"

    async def run():
        registry = ToolRegistry()
        registry.register("fail_text", "", {}, fail_with_text)
        registry.register("fail_exit", "", {}, fail_with_exit_code)
        registry.register("ok", "", {}, ok)
        text = await registry.execute(ToolCall(id="1", name="fail_text", arguments={}))
        exit_code = await registry.execute(ToolCall(id="2", name="fail_exit", arguments={}))
        success = await registry.execute(ToolCall(id="3", name="ok", arguments={}))
        return text, exit_code, success

    text, exit_code, success = asyncio.run(run())
    assert text.is_error
    assert exit_code.is_error
    assert not success.is_error


def test_duplicate_tool_registration_is_rejected():
    registry = ToolRegistry()
    registry.register("sample", "", {}, lambda: "OK")
    try:
        registry.register("sample", "", {}, lambda: "OK")
    except ValueError as exc:
        assert "Duplicate tool" in str(exc)
    else:
        raise AssertionError("duplicate tool registration was accepted")


def test_read_file_can_page_large_files():
    read_file = _load_tool_module("read_file")
    large_text = "".join(f"line {i}\n" for i in range(7000))

    async def run(path: str):
        return await read_file.execute(path=path, offset=6000, limit=3)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "large.txt"
        path.write_text(large_text, encoding="utf-8")
        result = asyncio.run(run(str(path)))

    assert "showing lines 6001-6003" in result
    assert "6001\tline 6000" in result
    assert "6003\tline 6002" in result


def test_web_fetch_rejects_local_network_targets():
    web_fetch = _load_tool_module("web_fetch")

    assert "localhost" in web_fetch._validate_url("http://localhost:8000")
    assert "loopback" in web_fetch._validate_url("http://127.0.0.1:8000")
    assert "private network" in web_fetch._validate_url("http://10.0.0.1")
    assert "scheme 'file'" in web_fetch._validate_url("file:///etc/passwd")


def test_memory_ops_reuses_store_crud_layout():
    memory_ops = _load_tool_module("memory_ops")
    old_home = os.environ.get("HOME")

    async def run():
        added = await memory_ops.execute(
            action="add",
            employee_id="emp",
            content="alpha memory content",
            evidence="unit test evidence",
            scope="project",
        )
        match = re.search(r"'([a-f0-9]{12})'", added)
        assert match, added
        memory_id = match.group(1)

        found = await memory_ops.execute(action="search", employee_id="emp", query="alpha")
        assert f"[{memory_id}] (project)" in found

        updated = await memory_ops.execute(
            action="update",
            employee_id="emp",
            memory_id=memory_id,
            content="beta memory content",
            evidence="updated evidence",
        )
        assert updated.startswith("OK: updated memory")

        removed = await memory_ops.execute(
            action="remove",
            employee_id="emp",
            memory_id=memory_id,
        )
        assert removed.startswith("OK: removed memory")

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            asyncio.run(run())
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    raise SystemExit(1 if failures else 0)

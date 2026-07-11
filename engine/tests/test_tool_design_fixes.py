from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import tempfile
from pathlib import Path

from engine.execution.agent_loop import _enabled_tools_from_config
from engine.identity_catalog import IdentitySpec
from engine.tool.interface import ToolCall
from engine.tool.registry import ToolRegistry


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


def test_tool_allowlist_filters_schema_prompt_and_execution():
    async def run():
        registry = ToolRegistry()
        registry.register("allowed", "", {}, lambda: "OK")
        registry.register("disabled", "", {}, lambda: "NOPE")

        unknown = registry.set_enabled(["allowed", "missing"])
        schemas = registry.get_schemas()
        tools = registry.list_tools()
        allowed = await registry.execute(ToolCall(id="1", name="allowed", arguments={}))
        disabled = await registry.execute(ToolCall(id="2", name="disabled", arguments={}))
        return unknown, schemas, tools, allowed, disabled

    unknown, schemas, tools, allowed, disabled = asyncio.run(run())

    assert unknown == ["missing"]
    assert [s["function"]["name"] for s in schemas] == ["allowed"]
    assert [t.name for t in tools] == ["allowed"]
    assert not allowed.is_error
    assert disabled.is_error
    assert "Tool disabled" in disabled.content


def test_web_tool_aliases_execute_canonical_tools():
    async def run():
        registry = ToolRegistry()
        registry.register("web_search", "", {}, lambda query: f"searched {query}")
        registry.register("web_fetch", "", {}, lambda url: f"fetched {url}")
        unknown_config = registry.set_enabled(["websearch", "webfetch"])
        schemas = registry.get_schemas()

        search = await registry.execute(
            ToolCall(id="1", name="websearch", arguments={"query": "docs"})
        )
        fetch = await registry.execute(
            ToolCall(id="2", name="webfetch", arguments={"url": "https://example.com"})
        )
        unknown = await registry.execute(
            ToolCall(id="3", name="web_lookup", arguments={"query": "docs"})
        )
        return unknown_config, schemas, search, fetch, unknown

    unknown_config, schemas, search, fetch, unknown = asyncio.run(run())

    assert unknown_config == []
    assert [s["function"]["name"] for s in schemas] == ["web_search", "web_fetch"]
    assert not search.is_error
    assert search.content == "searched docs"
    assert not fetch.is_error
    assert fetch.content == "fetched https://example.com"
    assert unknown.is_error
    assert "Unknown tool: web_lookup" in unknown.content


def test_agent_tool_config_hides_internal_and_stale_tools_by_default():
    registry = ToolRegistry()
    for name in [
        "read_file",
        "write_file",
        "skill_load",
        "skill_manage",
        "memory_ops",
        "todo",
    ]:
        registry.register(name, "", {}, lambda: "OK")

    enabled = _enabled_tools_from_config(
        {
            "tools": {
                "enabled": [
                    "read_file",
                    "skill_load",
                    "skill_manage",
                    "memory_ops",
                    "search_knowledge",
                    "todo",
                ]
            }
        },
        registry,
        IdentitySpec(
            id="smith",
            name="Smith",
            description="",
            prompt="",
            enabled_tools=None,
            enabled_skills=None,
            routes=(),
            is_default=True,
        ),
    )

    assert enabled == ["read_file", "todo"]


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


def test_web_fetch_plain_html_fallback_extracts_text():
    web_fetch = _load_tool_module("web_fetch")

    text = web_fetch._html_to_text(
        "<html><head><title>Title</title><style>.x{}</style></head>"
        "<body><h1>Hello</h1><script>alert(1)</script><p>World&nbsp;again</p></body></html>"
    )

    assert "Hello" in text
    assert "World again" in text
    assert "alert" not in text
    assert "<h1>" not in text


def test_memory_ops_reuses_store_crud_layout():
    memory_ops = _load_tool_module("memory_ops")
    old_home = os.environ.get("HOME")

    async def run():
        added = await memory_ops.execute(
            action="add",
            agent_id="smith",
            content="alpha memory content",
            evidence="unit test evidence",
            scope="project",
        )
        match = re.search(r"'([a-f0-9]{12})'", added)
        assert match, added
        memory_id = match.group(1)

        found = await memory_ops.execute(action="search", agent_id="smith", query="alpha")
        assert f"[{memory_id}] (project)" in found

        updated = await memory_ops.execute(
            action="update",
            agent_id="smith",
            memory_id=memory_id,
            content="beta memory content",
            evidence="updated evidence",
        )
        assert updated.startswith("OK: updated memory")

        removed = await memory_ops.execute(
            action="remove",
            agent_id="smith",
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

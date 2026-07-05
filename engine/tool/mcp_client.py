"""Minimal MCP STDIO client for tool discovery and execution.

Implements the Model Context Protocol (MCP) over JSON-RPC 2.0 on
stdin/stdout, supporting tool listing and invocation. Designed to
integrate with the existing ToolRegistry.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """A tool discovered from an MCP server."""

    name: str
    description: str
    input_schema: dict


class MCPClient:
    """STDIO-based MCP client that spawns and communicates with an MCP server."""

    def __init__(self, command: list[str], env: dict[str, str] | None = None) -> None:
        self._command = command
        self._env = env
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0

    async def connect(self) -> None:
        """Spawn the MCP server process and perform the initialize handshake."""
        self._process = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env,
        )
        await self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "agent-smith", "version": "0.2.0"},
        })
        log.info("MCP client connected to: %s", " ".join(self._command))

    async def list_tools(self) -> list[MCPTool]:
        """Discover available tools from the MCP server."""
        result = await self._send("tools/list", {})
        tools: list[MCPTool] = []
        for t in result.get("tools", []):
            tools.append(MCPTool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            ))
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the MCP server and return the text result."""
        result = await self._send("tools/call", {"name": name, "arguments": arguments})
        content_parts: list[dict] = result.get("content", [])
        return "\n".join(p.get("text", str(p)) for p in content_parts)

    def to_openai_schemas(self, tools: list[MCPTool]) -> list[dict]:
        """Convert MCP tools to OpenAI function calling format.

        Tool names are prefixed with ``mcp_`` to avoid collisions with
        locally registered tools.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": f"mcp_{t.name}",
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]

    # -- internal ----------------------------------------------------------

    async def _send(self, method: str, params: dict) -> dict:
        """Send a JSON-RPC 2.0 request and wait for the response."""
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("MCP client not connected — call connect() first")

        self._request_id += 1
        msg = json.dumps({
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        })
        self._process.stdin.write((msg + "\n").encode())
        await self._process.stdin.drain()

        line = await asyncio.wait_for(self._process.stdout.readline(), timeout=30)
        if not line:
            raise RuntimeError("MCP server closed stdout unexpectedly")
        resp = json.loads(line.decode())

        if "error" in resp:
            raise RuntimeError(f"MCP error: {resp['error']}")
        return resp.get("result", {})

    async def close(self) -> None:
        """Shut down the MCP server process."""
        if self._process is None:
            return
        if self._process.stdin:
            self._process.stdin.close()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=5)
        except asyncio.TimeoutError:
            self._process.kill()
            log.warning("MCP server killed after timeout")
        self._process = None


async def register_mcp_tools(registry: Any, client: MCPClient) -> int:
    """Discover MCP tools and register them into a ToolRegistry.

    Each tool is registered with an ``mcp_`` prefix to avoid name
    collisions. Returns the number of tools registered.
    """
    tools = await client.list_tools()
    count = 0
    for tool in tools:
        # 闭包捕获 — 使用默认参数绑定当前迭代值
        async def _execute(*, _client: MCPClient = client, _name: str = tool.name, **kwargs: Any) -> str:
            return await _client.call_tool(_name, kwargs)

        registry.register(
            name=f"mcp_{tool.name}",
            description=tool.description,
            parameters=tool.input_schema,
            func=_execute,
        )
        count += 1

    log.info("Registered %d MCP tools from %s", count, " ".join(client._command))
    return count

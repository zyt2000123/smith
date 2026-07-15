from __future__ import annotations

import asyncio

from engine.mcp.client import MCPTool
from engine.mcp.session_pool import MCPClientSessionPool


class FakeClient:
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def test_session_pool_reuses_discovered_tools_and_closes_on_release() -> None:
    async def run():
        created: list[FakeClient] = []

        async def connect(config: dict):
            client = FakeClient(str(config["name"]))
            created.append(client)
            return client, [MCPTool("search", "search docs", {"type": "object"})]

        pool = MCPClientSessionPool(connect_server=connect)
        config = [{"type": "stdio", "name": "docs", "command": ["docs-server"]}]

        first = await pool.acquire("session-1", config)
        second = await pool.acquire("session-1", config)
        await pool.release("session-1")

        return created, first, second

    created, first, second = asyncio.run(run())

    assert len(created) == 1
    assert first[0].client is second[0].client
    assert first[0].tools[0].name == "search"
    assert created[0].closed is True


def test_session_pool_replaces_connections_when_server_config_changes() -> None:
    async def run():
        created: list[FakeClient] = []

        async def connect(config: dict):
            client = FakeClient(str(config["name"]))
            created.append(client)
            return client, [MCPTool("search", "", {})]

        pool = MCPClientSessionPool(connect_server=connect)
        original = [{"type": "stdio", "name": "docs", "command": ["v1"]}]
        changed = [{"type": "stdio", "name": "docs", "command": ["v2"]}]

        first = await pool.acquire("session-1", original)
        second = await pool.acquire("session-1", changed)
        await pool.close()
        return created, first, second

    created, first, second = asyncio.run(run())

    assert len(created) == 2
    assert first[0].client is not second[0].client
    assert created[0].closed is True
    assert created[1].closed is True

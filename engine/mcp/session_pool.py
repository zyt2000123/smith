"""Session-scoped ownership and reuse of MCP client connections."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from engine.mcp.client import MCPClient, MCPTool
from engine.mcp.config import mcp_server_log_summary, mcp_tool_prefix_from_config, mcp_transport_from_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionMCPServer:
    """One connected MCP server plus its discovery snapshot."""

    client: MCPClient
    prefix: str
    tools: list[MCPTool]


@dataclass
class _SessionEntry:
    fingerprint: str
    servers: list[SessionMCPServer]


ConnectServer = Callable[[dict[str, Any]], Awaitable[tuple[MCPClient, list[MCPTool]]]]


class MCPClientSessionPool:
    """Keep MCP connections alive for one conversation session.

    A runtime receives borrowed clients from this pool; it must never close
    them.  Session deletion and process shutdown own cleanup instead.
    """

    def __init__(self, *, connect_server: ConnectServer | None = None) -> None:
        self._connect_server = connect_server or _connect_server
        self._entries: dict[str, _SessionEntry] = {}
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        session_id: str,
        configured_servers: list[dict[str, Any]],
    ) -> list[SessionMCPServer]:
        """Return cached servers or replace them when configuration changed."""
        fingerprint = _fingerprint(configured_servers)
        stale: list[SessionMCPServer] = []
        async with self._lock:
            current = self._entries.get(session_id)
            if current is not None and current.fingerprint == fingerprint:
                return current.servers

            servers = await self._connect_all(configured_servers)
            if current is not None:
                stale = current.servers
            self._entries[session_id] = _SessionEntry(fingerprint, servers)

        await _close_servers(stale)
        return servers

    async def release(self, session_id: str) -> None:
        """Close all MCP connections owned by a deleted conversation."""
        async with self._lock:
            entry = self._entries.pop(session_id, None)
        if entry is not None:
            await _close_servers(entry.servers)

    async def close(self) -> None:
        """Close every session connection during process shutdown."""
        async with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for entry in entries:
            await _close_servers(entry.servers)

    async def _connect_all(self, configured_servers: list[dict[str, Any]]) -> list[SessionMCPServer]:
        servers: list[SessionMCPServer] = []
        for config in configured_servers:
            try:
                client, tools = await self._connect_server(config)
                servers.append(SessionMCPServer(
                    client=client,
                    prefix=mcp_tool_prefix_from_config(config),
                    tools=tools,
                ))
            except Exception:
                logger.exception(
                    "failed to connect session MCP server: %r",
                    mcp_server_log_summary(config),
                )
        return servers


async def _connect_server(config: dict[str, Any]) -> tuple[MCPClient, list[MCPTool]]:
    transport = mcp_transport_from_config(config)
    if transport is None:
        raise ValueError("invalid MCP transport configuration")
    client = MCPClient(transport=transport)
    try:
        await client.connect()
        return client, await client.list_tools()
    except BaseException:
        await client.close()
        raise


async def _close_servers(servers: list[SessionMCPServer]) -> None:
    for server in reversed(servers):
        try:
            await server.client.close()
        except Exception:
            logger.warning("failed to close session MCP client", exc_info=True)


def _fingerprint(configured_servers: list[dict[str, Any]]) -> str:
    """Create an in-memory stable key; it is never logged or persisted."""
    return json.dumps(configured_servers, sort_keys=True, separators=(",", ":"), default=str)

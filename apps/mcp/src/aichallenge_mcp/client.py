"""Official MCP client: initialize + list_tools (stdio or Streamable HTTP)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from aichallenge_mcp.server import EXPECTED_TOOL_NAMES, SERVER_NAME


@dataclass(frozen=True)
class McpToolRow:
    name: str
    description: str


@dataclass(frozen=True)
class McpListResult:
    transport: str
    connected: bool
    server: str
    tools: tuple[McpToolRow, ...]


async def list_tools_stdio() -> McpListResult:
    src = Path(__file__).resolve().parent.parent
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "aichallenge_mcp"],
        env={**os.environ, "PYTHONPATH": str(src), "MCP_TRANSPORT": "stdio"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            listed = await session.list_tools()
    return McpListResult(
        transport="stdio",
        connected=True,
        server=init.serverInfo.name,
        tools=tuple(
            McpToolRow(tool.name, (tool.description or "").strip()) for tool in listed.tools
        ),
    )


async def list_tools_http(url: str, token: str) -> McpListResult:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with streamablehttp_client(url, headers=headers) as (read, write, _session_id):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            listed = await session.list_tools()
    return McpListResult(
        transport="http",
        connected=True,
        server=init.serverInfo.name,
        tools=tuple(
            McpToolRow(tool.name, (tool.description or "").strip()) for tool in listed.tools
        ),
    )


def render(result: McpListResult) -> str:
    lines = [
        f"initialized: yes",
        f"transport:   {result.transport}",
        f"server:      {result.server or SERVER_NAME}",
        f"tools:       {len(result.tools)}",
        "",
        f"{'name':<14} description",
        f"{'-' * 14} {'-' * 48}",
    ]
    for tool in result.tools:
        lines.append(f"{tool.name:<14} {tool.description}")
    names = {tool.name for tool in result.tools}
    extra = names - EXPECTED_TOOL_NAMES
    missing = EXPECTED_TOOL_NAMES - names
    lines.append("")
    if extra or missing:
        lines.append(f"check: FAIL missing={sorted(missing)} extra={sorted(extra)}")
    else:
        lines.append("check: OK expected tools present")
    return "\n".join(lines)

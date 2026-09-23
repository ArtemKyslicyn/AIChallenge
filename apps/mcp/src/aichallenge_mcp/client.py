"""Official MCP client: initialize, list_tools, call_tool (stdio or Streamable HTTP)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


@dataclass(frozen=True)
class McpCallResult:
    name: str
    result: str
    is_error: bool = False


def _stdio_params() -> StdioServerParameters:
    src = Path(__file__).resolve().parent.parent
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "aichallenge_mcp"],
        env={**os.environ, "PYTHONPATH": str(src), "MCP_TRANSPORT": "stdio"},
    )


def _text_from_call(result: Any) -> str:
    chunks: list[str] = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text:
            chunks.append(str(text))
    if chunks:
        return "\n".join(chunks)
    return str(result)


async def list_tools_stdio() -> McpListResult:
    async with stdio_client(_stdio_params()) as (read, write):
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


async def call_tool_stdio(name: str, arguments: dict[str, Any] | None = None) -> McpCallResult:
    async with stdio_client(_stdio_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.call_tool(name, arguments or {})
    return McpCallResult(
        name=name,
        result=_text_from_call(listed),
        is_error=bool(getattr(listed, "isError", False)),
    )


async def call_tool_http(
    url: str,
    token: str,
    name: str,
    arguments: dict[str, Any] | None = None,
) -> McpCallResult:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with streamablehttp_client(url, headers=headers) as (read, write, _session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.call_tool(name, arguments or {})
    return McpCallResult(
        name=name,
        result=_text_from_call(listed),
        is_error=bool(getattr(listed, "isError", False)),
    )


def render(result: McpListResult) -> str:
    lines = [
        f"initialized: yes",
        f"transport:   {result.transport}",
        f"server:      {result.server or SERVER_NAME}",
        f"tools:       {len(result.tools)}",
        "",
        f"{'name':<18} description",
        f"{'-' * 18} {'-' * 48}",
    ]
    for tool in result.tools:
        lines.append(f"{tool.name:<18} {tool.description}")
    names = {tool.name for tool in result.tools}
    missing = EXPECTED_TOOL_NAMES - names
    lines.append("")
    if missing:
        lines.append(f"check: FAIL missing={sorted(missing)}")
    else:
        extra = names - EXPECTED_TOOL_NAMES
        extra_note = f" extra={sorted(extra)}" if extra else ""
        lines.append(f"check: OK expected tools present{extra_note}")
    return "\n".join(lines)

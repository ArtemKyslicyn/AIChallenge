"""Day 16: official client initializes and lists tools over stdio (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from aichallenge_mcp.server import EXPECTED_TOOL_NAMES, PULSE_TOOL_NAMES

SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.mark.asyncio
async def test_stdio_initialize_and_list_tools() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "aichallenge_mcp"],
        env={"PYTHONPATH": str(SRC), "MCP_TRANSPORT": "stdio"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.serverInfo.name == "aichallenge-mcp"
            listed = await session.list_tools()
    names = {tool.name for tool in listed.tools}
    assert EXPECTED_TOOL_NAMES <= names
    assert PULSE_TOOL_NAMES <= names
    assert all((tool.description or "").strip() for tool in listed.tools)

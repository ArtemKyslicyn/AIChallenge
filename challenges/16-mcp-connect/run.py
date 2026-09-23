#!/usr/bin/env python3
"""Challenge 16 — connect to MCP and print the tool catalog."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MCP_SRC = ROOT / "apps" / "mcp" / "src"
sys.path.insert(0, str(MCP_SRC))

from aichallenge_mcp.client import list_tools_http, list_tools_stdio, render  # noqa: E402
from aichallenge_mcp.server import EXPECTED_TOOL_NAMES  # noqa: E402

DEFAULT_REMOTE = os.environ.get("MCP_URL", "https://aichallenge.arcilite.ru/mcp")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP initialize + list_tools")
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="local stdio server (default when MCP_SHARED_TOKEN is empty)",
    )
    parser.add_argument("--url", default=DEFAULT_REMOTE, help="Streamable HTTP MCP URL")
    parser.add_argument(
        "--token",
        default=os.environ.get("MCP_SHARED_TOKEN", ""),
        help="Bearer token (or env MCP_SHARED_TOKEN)",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    use_stdio = args.stdio or not args.token
    if use_stdio:
        print("MCP transport: stdio (local server)")
        result = await list_tools_stdio()
    else:
        print(f"MCP transport: http\nMCP url: {args.url}\nMCP token: set")
        result = await list_tools_http(args.url, args.token)
    text = render(result)
    print(text)
    names = {tool.name for tool in result.tools}
    ok = result.connected and EXPECTED_TOOL_NAMES <= names
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "transport": result.transport,
        "server": result.server,
        "connected": result.connected,
        "tools": [{"name": t.name, "description": t.description} for t in result.tools],
        "checks": {
            "initialized": result.connected,
            "tools_match": EXPECTED_TOOL_NAMES <= names,
        },
    }
    (HERE / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (HERE / "RESULTS.md").write_text(
        "# Challenge 16 — MCP connect\n\n"
        f"- transport: `{result.transport}`\n"
        f"- initialized: `{result.connected}`\n"
        f"- tools: {', '.join(sorted(names))}\n"
        f"- checks: initialized={payload['checks']['initialized']} "
        f"tools_match={payload['checks']['tools_match']}\n"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

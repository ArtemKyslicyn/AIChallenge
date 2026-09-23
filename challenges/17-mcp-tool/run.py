#!/usr/bin/env python3
"""Challenge 17 — call probe_stand / model_pulse and print the result."""

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

from aichallenge_mcp.client import call_tool_http, call_tool_stdio, list_tools_http, list_tools_stdio  # noqa: E402

DEFAULT_REMOTE = os.environ.get("MCP_URL", "https://aichallenge.arcilite.ru/mcp")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP call_tool: probe_stand")
    parser.add_argument("--stdio", action="store_true")
    parser.add_argument("--url", default=DEFAULT_REMOTE)
    parser.add_argument("--token", default=os.environ.get("MCP_SHARED_TOKEN", ""))
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    use_stdio = args.stdio or not args.token
    if use_stdio:
        listed = await list_tools_stdio()
        probe = await call_tool_stdio("probe_stand")
        pulse = await call_tool_stdio("model_pulse", {"hours": 24})
    else:
        listed = await list_tools_http(args.url, args.token)
        probe = await call_tool_http(args.url, args.token, "probe_stand")
        pulse = await call_tool_http(args.url, args.token, "model_pulse", {"hours": 24})
    names = {tool.name for tool in listed.tools}
    ok = {"probe_stand", "model_pulse"} <= names and not probe.is_error
    print(f"tools: {', '.join(sorted(names))}")
    print(f"probe_stand: {probe.result}")
    print(f"model_pulse: {pulse.result[:400]}")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "transport": listed.transport,
        "tools": sorted(names),
        "probe_stand": probe.result,
        "model_pulse": pulse.result,
        "checks": {
            "tools_registered": {"probe_stand", "model_pulse"} <= names,
            "probe_returned": not probe.is_error and bool(probe.result),
        },
    }
    (HERE / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (HERE / "RESULTS.md").write_text(
        "# Challenge 17 — MCP tool\n\n"
        f"- tools: {', '.join(sorted(names))}\n"
        f"- probe_stand: `{probe.result[:180]}`\n"
        f"- checks: tools_registered={payload['checks']['tools_registered']} "
        f"probe_returned={payload['checks']['probe_returned']}\n"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

#!/usr/bin/env python3
"""Challenge 19 — search → summarize → saveToFile, passing JSON between tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MCP_SRC = ROOT / "apps" / "mcp" / "src"
sys.path.insert(0, str(MCP_SRC))

os.environ.setdefault("MCP_DATA_DIR", tempfile.mkdtemp(prefix="pulse-19-"))

from aichallenge_mcp.client import call_tool_http, call_tool_stdio, list_tools_http, list_tools_stdio  # noqa: E402

DEFAULT_REMOTE = os.environ.get("MCP_URL", "https://aichallenge.arcilite.ru/mcp")
NEEDED = {"search", "summarize", "saveToFile"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP pipeline: search → summarize → saveToFile")
    parser.add_argument("--stdio", action="store_true")
    parser.add_argument("--url", default=DEFAULT_REMOTE)
    parser.add_argument("--token", default=os.environ.get("MCP_SHARED_TOKEN", ""))
    return parser.parse_args()


def _parse(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


async def main() -> int:
    args = parse_args()
    use_stdio = args.stdio or not args.token
    if use_stdio:
        listed = await list_tools_stdio()
        collected = await call_tool_stdio("search", {"hours": 24})
        summarized = await call_tool_stdio("summarize", {"payload": collected.result})
        saved = await call_tool_stdio("saveToFile", {"brief": summarized.result, "name": "night-brief"})
    else:
        listed = await list_tools_http(args.url, args.token)
        collected = await call_tool_http(args.url, args.token, "search", {"hours": 24})
        summarized = await call_tool_http(
            args.url, args.token, "summarize", {"payload": collected.result}
        )
        saved = await call_tool_http(
            args.url,
            args.token,
            "saveToFile",
            {"brief": summarized.result, "name": "night-brief"},
        )
    names = {tool.name for tool in listed.tools}
    search_body = _parse(collected.result)
    summary_body = _parse(summarized.result)
    save_body = _parse(saved.result)
    path = Path(str(save_body.get("path") or ""))
    checks = {
        "tools_registered": NEEDED <= names,
        "search_source": search_body.get("source") == "search" and "health" in search_body,
        "summarize_from_search": summary_body.get("source") == "summarize"
        and summary_body.get("from") == "search",
        "saved_from_summarize": save_body.get("source") == "saveToFile"
        and save_body.get("from") == "summarize"
        and path.is_file(),
    }
    ok = all(checks.values()) and not (collected.is_error or summarized.is_error or saved.is_error)
    print(f"tools: {', '.join(sorted(names))}")
    print(f"search: {collected.result[:240]}")
    print(f"summarize: {summarized.result[:240]}")
    print(f"saveToFile: {saved.result}")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "transport": listed.transport,
        "tools": sorted(names),
        "search": search_body,
        "summarize": summary_body,
        "saveToFile": save_body,
        "checks": checks,
    }
    (HERE / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (HERE / "RESULTS.md").write_text(
        "# Challenge 19 — MCP compose\n\n"
        f"- tools: {', '.join(sorted(NEEDED))}\n"
        f"- search.source: `{search_body.get('source')}`\n"
        f"- summarize.from: `{summary_body.get('from')}`\n"
        f"- saveToFile.path: `{save_body.get('path')}`\n"
        f"- checks: search={checks['search_source']} "
        f"summarize={checks['summarize_from_search']} "
        f"save={checks['saved_from_summarize']}\n"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

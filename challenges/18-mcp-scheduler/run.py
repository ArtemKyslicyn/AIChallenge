#!/usr/bin/env python3
"""Challenge 18 — schedule a digest, persist SQLite, return aggregate."""

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

from aichallenge_mcp.client import call_tool_http, call_tool_stdio  # noqa: E402

DEFAULT_REMOTE = os.environ.get("MCP_URL", "https://aichallenge.arcilite.ru/mcp")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP schedule_digest + latest_digest")
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
    arguments = {"interval_seconds": 60, "hours": 24, "note": "challenge-18"}
    if use_stdio:
        scheduled = await call_tool_stdio("schedule_digest", arguments)
        latest = await call_tool_stdio("latest_digest")
        jobs = await call_tool_stdio("list_jobs")
    else:
        scheduled = await call_tool_http(args.url, args.token, "schedule_digest", arguments)
        latest = await call_tool_http(args.url, args.token, "latest_digest")
        jobs = await call_tool_http(args.url, args.token, "list_jobs")
    scheduled_body = _parse(scheduled.result)
    latest_body = _parse(latest.result)
    jobs_body = _parse(jobs.result)
    digest = scheduled_body.get("first_digest") or latest_body.get("digest") or {}
    ok = bool(scheduled_body.get("job_id") and digest.get("summary") and jobs_body.get("count", 0) >= 1)
    print(scheduled.result)
    print(latest.result)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schedule": scheduled_body,
        "latest": latest_body,
        "jobs": jobs_body,
        "checks": {
            "job_persisted": bool(scheduled_body.get("job_id")),
            "digest_returned": bool(digest.get("summary")),
            "jobs_listed": int(jobs_body.get("count") or 0) >= 1,
        },
    }
    (HERE / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (HERE / "RESULTS.md").write_text(
        "# Challenge 18 — scheduler\n\n"
        f"- job_id: `{scheduled_body.get('job_id')}`\n"
        f"- interval: `{scheduled_body.get('interval_seconds')}`\n"
        f"- summary: {digest.get('summary')}\n"
        f"- checks: job_persisted={payload['checks']['job_persisted']} "
        f"digest_returned={payload['checks']['digest_returned']}\n"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

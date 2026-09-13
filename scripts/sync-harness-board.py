#!/usr/bin/env python3
"""Refresh configs/benchmarks/harness_board.json from upstream README.

No API keys. Usage (from repo root):

    python3 scripts/sync-harness-board.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

README_URL = (
    "https://raw.githubusercontent.com/ai-forever/harness-bench-fast/main/README.md"
)
OUT = Path(__file__).resolve().parents[1] / "configs" / "benchmarks" / "harness_board.json"
SOURCE = "https://github.com/ai-forever/harness-bench-fast"
LANDING = "https://ai-forever.github.io/harness-bench-fast/"


def _num(raw: str) -> int | None:
    text = raw.strip().replace(",", "")
    if text in {"", "-", "—", "–"}:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_readme(text: str) -> list[dict]:
    lines = text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        if line.startswith("| Harness") and "Result" in line:
            start = i
            break
    if start is None:
        raise SystemExit("harness-bench README table not found")

    rows: list[dict] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 7:
            continue
        harness, profile, model, result, pct, steps, tokens = parts[:7]
        match = re.match(r"(\d+)\s*/\s*(\d+)", result.replace(",", ""))
        if not match:
            continue
        passed, total = int(match.group(1)), int(match.group(2))
        pct_match = re.match(r"([\d.]+)\s*%", pct.replace(",", ""))
        pct_f = float(pct_match.group(1)) if pct_match else round(100.0 * passed / total, 1)
        rows.append(
            {
                "harness": harness,
                "profile": None if profile in {"—", "-"} else profile,
                "model_label": model,
                "passed": passed,
                "total": total,
                "pct": pct_f,
                "steps": _num(steps),
                "tokens": _num(tokens),
                "source": SOURCE,
            }
        )
    if not rows:
        raise SystemExit("no leaderboard rows parsed")
    return rows


def main() -> int:
    with urllib.request.urlopen(README_URL, timeout=60) as resp:
        text = resp.read().decode()
    rows = parse_readme(text)
    total_tasks = max((r["total"] for r in rows), default=391)
    board = {
        "task_set": "v0.16.0",
        "total_tasks": total_tasks,
        "source_url": SOURCE,
        "landing_url": LANDING,
        "updated_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(rows)} rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

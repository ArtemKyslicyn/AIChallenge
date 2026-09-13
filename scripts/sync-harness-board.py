#!/usr/bin/env python3
"""Refresh configs/benchmarks/harness_board.json from upstream README.

No API keys. Usage (from repo root or /opt/aichallenge):

    python3 scripts/sync-harness-board.py
    python3 scripts/sync-harness-board.py /path/to/harness_board.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running on the VPS without installing the API package.
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "configs" / "benchmarks" / "harness_board.json"


def _sync_via_stdlib(out: Path) -> int:
    import re
    import urllib.request
    from datetime import UTC, datetime

    url = "https://raw.githubusercontent.com/ai-forever/harness-bench-fast/main/README.md"
    source = "https://github.com/ai-forever/harness-bench-fast"
    landing = "https://ai-forever.github.io/harness-bench-fast/"
    req = urllib.request.Request(url, headers={"User-Agent": "aichallenge-harness-board-sync/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode()

    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("| Harness") and "Result" in line),
        None,
    )
    if start is None:
        print("README table not found", file=sys.stderr)
        return 1

    def num(raw: str) -> int | None:
        text = raw.strip().replace(",", "")
        if text in {"", "-", "—", "–"}:
            return None
        try:
            return int(text)
        except ValueError:
            return None

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
                "steps": num(steps),
                "tokens": num(tokens),
                "source": source,
            }
        )
    if not rows:
        print("no rows parsed", file=sys.stderr)
        return 1

    board = {
        "task_set": "v0.16.0",
        "total_tasks": max(r["total"] for r in rows),
        "source_url": source,
        "landing_url": landing,
        "updated_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(rows)} rows)", file=sys.stderr)
    return 0


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    return _sync_via_stdlib(out)


if __name__ == "__main__":
    raise SystemExit(main())

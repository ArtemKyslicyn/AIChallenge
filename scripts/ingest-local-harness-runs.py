#!/usr/bin/env python3
"""Merge local harness-bench full-run JSONs into configs/benchmarks/harness_board.json.

Local rows are tagged source=local-harness-run so they do not collide with
upstream README sync (re-sync still preserves them if you pass --keep-local).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "configs" / "benchmarks" / "harness_board.json"
DEFAULT_RESULTS = Path("/Users/arcilite/Documents/harness-bench-fast/results/full")


def _pct(passed: int, total: int) -> float:
    return round(100.0 * passed / total, 1) if total else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--board", type=Path, default=BOARD)
    parser.add_argument(
        "--min-total",
        type=int,
        default=391,
        help="Only ingest runs that reached this many tasks (default: full set).",
    )
    args = parser.parse_args()

    board = json.loads(args.board.read_text()) if args.board.exists() else {
        "task_set": "v0.16.0",
        "total_tasks": 391,
        "source_url": "https://github.com/ai-forever/harness-bench-fast",
        "landing_url": "https://ai-forever.github.io/harness-bench-fast/",
        "updated_at": "",
        "rows": [],
    }

    rows = [r for r in board.get("rows", []) if r.get("source") != "local-harness-run"]
    ingested = 0

    for meta_path in sorted(args.results_dir.glob("*.meta.json")):
        run_id = meta_path.name.replace(".meta.json", "")
        json_path = args.results_dir / f"{run_id}.json"
        if not json_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        data = json.loads(json_path.read_text())
        total = int(data.get("total") or 0)
        passed = int(data.get("passed") or 0)
        if total < args.min_total:
            print(f"skip incomplete {run_id}: {passed}/{total}")
            continue
        chain_id = meta.get("chain_model_id") or meta.get("openrouter_model_id")
        label = chain_id  # keep provider id as label for tight matching
        rows.append(
            {
                "harness": "deepagents",
                "profile": "none",
                "model_label": label,
                "passed": passed,
                "total": total,
                "pct": _pct(passed, total),
                "steps": data.get("steps"),
                "tokens": data.get("tokens"),
                "source": "local-harness-run",
            }
        )
        ingested += 1
        print(f"ingest {chain_id}: {passed}/{total} ({_pct(passed, total)}%)")

    board["rows"] = rows
    board["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    args.board.parent.mkdir(parents=True, exist_ok=True)
    args.board.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {args.board} (+{ingested} local rows, total {len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

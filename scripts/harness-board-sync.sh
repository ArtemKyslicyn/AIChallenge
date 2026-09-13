#!/usr/bin/env bash
# Daily (or on-demand) refresh of harness-bench leaderboard snapshot.
# Safe for systemd timer / cron. No secrets.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${HARNESS_BOARD_PATH:-$ROOT/configs/benchmarks/harness_board.json}"
python3 "$ROOT/scripts/sync-harness-board.py" "$OUT"

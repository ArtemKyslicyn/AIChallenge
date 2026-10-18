#!/usr/bin/env bash
# Local advisory review. Exit 1 only on secret findings.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-HEAD}"
exec python3 "$ROOT/scripts/review/cli.py" "$BASE"

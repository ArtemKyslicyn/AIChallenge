#!/usr/bin/env bash
# Local quality gate for conflict-emulation static site.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0
need() { [[ -f "$1" ]] || { echo "MISSING $1"; fail=1; }; }

need index.html
need styles/host-shim.css
need scripts/app.js
need views/llm-board.fragment.html
need views/planet.fragment.html
need views/parchment.fragment.html
need views/arcs.fragment.html

# Fragments must be self-contained enough to mount
for f in views/*.fragment.html; do
  if ! grep -q '<script>' "$f"; then
    echo "WARN $f has no inline script (ok for some)"
  fi
  if grep -qiE 'fetch\(|XMLHttpRequest|https?://cdn' "$f"; then
    echo "FAIL $f uses network/CDN"
    fail=1
  fi
done

# Host shim tokens present
grep -q 'vis-button' styles/host-shim.css || { echo "FAIL host-shim missing vis-button"; fail=1; }

# Index wires all views
for v in llm planet parchment arcs about; do
  grep -q "data-view=\"$v\"" index.html || { echo "FAIL index missing tab $v"; fail=1; }
done

if [[ "$fail" -ne 0 ]]; then
  echo "QUALITY FAIL"
  exit 1
fi
echo "QUALITY PASS (static checks)"

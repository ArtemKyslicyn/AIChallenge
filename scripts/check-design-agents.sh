#!/usr/bin/env bash
# Cross-check: Cursor design-review agents are present and parseable.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS=(
  designer-visual
  designer-interaction
  designer-density
  designer-a11y
  designer-brand
  design-lead
)
missing=0
for name in "${AGENTS[@]}"; do
  f="$ROOT/.cursor/agents/${name}.md"
  if [[ ! -f "$f" ]]; then
    echo "MISSING $f"
    missing=1
    continue
  fi
  if ! grep -q "^name: ${name}$" "$f"; then
    echo "BAD frontmatter name in $f"
    missing=1
    continue
  fi
  if ! grep -q "^description:" "$f"; then
    echo "BAD frontmatter description in $f"
    missing=1
    continue
  fi
  lines=$(wc -l < "$f" | tr -d ' ')
  if [[ "$lines" -lt 8 ]]; then
    echo "TOO SHORT $f"
    missing=1
    continue
  fi
  echo "OK $name"
done
cmd="$ROOT/.cursor/commands/design-review.md"
if [[ ! -f "$cmd" ]]; then
  echo "MISSING $cmd"
  missing=1
else
  echo "OK design-review command"
fi
exit "$missing"

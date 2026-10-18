#!/usr/bin/env python3
"""Day 32 acceptance: fixture diff → three markdown sections; secrets exit 1."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bad.diff"


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/review/cli.py"), "--diff-file", str(FIXTURE)],
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout
    print(out)
    for section in ("## Bugs", "## Architecture", "## Recommendations"):
        if section not in out:
            print(f"MISSING {section}", file=sys.stderr)
            return 2
    if "<!-- aichallenge-ai-review -->" not in out:
        print("MISSING marker", file=sys.stderr)
        return 2
    if proc.returncode != 1:
        print(f"expected exit 1 for secrets, got {proc.returncode}", file=sys.stderr)
        return 2
    print("PASS challenge 32")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

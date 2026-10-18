#!/usr/bin/env python3
"""CLI: review git diff or a fixture file."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from rubric import review_diff  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIChallenge invariant review")
    parser.add_argument(
        "base",
        nargs="?",
        default="HEAD",
        help="git ref for `git diff <base>` (working tree vs base)",
    )
    parser.add_argument("--diff-file", type=Path, help="Review a unified diff file instead of git")
    parser.add_argument("--staged", action="store_true", help="git diff --cached")
    args = parser.parse_args(argv)

    if args.diff_file:
        diff = args.diff_file.read_text(encoding="utf-8")
    else:
        cmd = ["git", "diff"]
        if args.staged:
            cmd.append("--cached")
        else:
            cmd.append(args.base)
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode not in (0, 1):
            print(proc.stderr or "git diff failed", file=sys.stderr)
            return 2
        diff = proc.stdout

    report = review_diff(diff)
    print(report.markdown())
    if report.has_blocking_secrets:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

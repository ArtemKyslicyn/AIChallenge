"""Offline score table for day 29. The live pair is recorded by hand."""

from __future__ import annotations

import sys


def score(text: str) -> int:
    low = text.lower()
    ports = "443" in text and "8443" in text and "18080" in text
    forbid = any(word in low for word in ("нельзя", "запрещ"))
    if ports and forbid:
        return 2
    if ("8443" in text or "xray" in low) and forbid:
        return 1
    return 0


def main() -> int:
    before = "обычный https. docker compose down --rmi all"
    after = "443 идёт в xray, затем nginx :8443, web :18080. compose down нельзя"
    rows = (
        ("before", 0.8, 220, score(before), "Q4_K_M"),
        ("after", 0.15, 180, score(after), "Q4_K_M"),
    )
    print("label\ttemperature\tnum_predict\tfaithfulness\tquant")
    for label, temperature, num_predict, faithfulness, quant in rows:
        print(f"{label}\t{temperature}\t{num_predict}\t{faithfulness}\t{quant}")
    if "--score-only" in sys.argv:
        assert rows[0][3] == 0
        assert rows[1][3] == 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

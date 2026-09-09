#!/usr/bin/env python3
"""Challenge 08 — agent token meter: short / long / overflow truncate."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _lib.prod_client import (  # noqa: E402
    DEFAULT_BASE,
    agent_dialog_clear,
    agent_run,
    write_json,
)

HERE = Path(__file__).resolve().parent
DRAFT = "challenge-08-tokens"
MODEL = os.environ.get("CHALLENGE_AGENT_MODEL", "google/gemini-2.5-flash")
SYSTEM = (
    "Ты агент учёта токенов. Отвечай коротко (1–3 предложения), без списков."
)
NAME = "Токен-метр · День 8"


def _tok(result: dict) -> dict:
    t = result.get("tokens") or {}
    if not t:
        raise SystemExit(f"missing tokens in response: {result!r}")
    return t


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    print(f"==> challenge 08 tokens @ {base} model={MODEL}")

    try:
        agent_dialog_clear(base, DRAFT)
    except Exception as exc:  # noqa: BLE001
        print(f"  clear skipped: {exc}")

    # A — short dialog
    short_msg = (HERE / "prompt.txt").read_text(encoding="utf-8").strip()
    a = agent_run(
        base,
        short_msg,
        system_prompt=SYSTEM,
        name=NAME,
        preferred_model=MODEL,
        temperature=0.2,
        max_tokens=120,
        persist=True,
        client_draft_id=DRAFT,
        context_limit=8192,
        timeout=180.0,
    )
    ta = _tok(a)
    print(
        f"  A short total={ta['total']} hist={ta['history_after']} "
        f"trunc={ta['truncation']['applied']}"
    )
    if ta["truncation"]["applied"]:
        raise SystemExit("A: unexpected truncation on short dialog")

    # B — long dialog (several fat turns)
    dialog_id = a.get("dialog_id")
    fat = ("факт-" + ("яблоко " * 40)).strip()
    tb_series = [ta]
    for i in range(4):
        b = agent_run(
            base,
            f"Запомни блок {i + 1}: {fat}. Подтверди номер блока.",
            system_prompt=SYSTEM,
            name=NAME,
            preferred_model=MODEL,
            temperature=0.2,
            max_tokens=80,
            persist=True,
            client_draft_id=DRAFT,
            dialog_id=str(dialog_id) if dialog_id else None,
            context_limit=8192,
            timeout=180.0,
        )
        dialog_id = b.get("dialog_id") or dialog_id
        tb = _tok(b)
        tb_series.append(tb)
        print(
            f"  B{i + 1} total={tb['total']} hist_before={tb['history_before']} "
            f"hist_after={tb['history_after']}"
        )

    if tb_series[-1]["history_before"] <= tb_series[0]["history_after"]:
        raise SystemExit("B: history did not grow across long dialog")

    # C — overflow with tiny context_limit
    c = agent_run(
        base,
        "Что ты помнишь из самых первых блоков? Если забыла — скажи, что контекст обрезан.",
        system_prompt=SYSTEM,
        name=NAME,
        preferred_model=MODEL,
        temperature=0.1,
        max_tokens=120,
        persist=True,
        client_draft_id=DRAFT,
        dialog_id=str(dialog_id) if dialog_id else None,
        context_limit=200,
        timeout=180.0,
    )
    tc = _tok(c)
    print(
        f"  C overflow trunc={tc['truncation']['applied']} "
        f"dropped={tc['truncation']['dropped_messages']} "
        f"hist {tc['history_before']}→{tc['history_after']} total={tc['total']}"
    )
    if not tc["truncation"]["applied"]:
        raise SystemExit("C: expected truncation under context_limit=200")
    if tc["history_after"] >= tc["history_before"]:
        raise SystemExit("C: history_after should be < history_before")

    payload = {
        "challenge": "08-tokens",
        "base_url": base,
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "cases": {
            "A_short": {"tokens": ta, "result": a},
            "B_long": {"tokens_series": tb_series[1:], "grew": True},
            "C_overflow": {"tokens": tc, "result": c},
        },
        "ok": True,
        "ui": "https://aichallenge.arcilite.ru/?shell=agents",
    }
    write_json(str(HERE / "results.json"), payload)

    md = [
        "# Challenge 08 — Token Meter",
        "",
        f"Prod: `{base}` · {payload['ts']}",
        "",
        f"- Model: `{MODEL}`",
        f"- A short total={ta['total']} (no truncate)",
        f"- B long history grew → {tb_series[-1]['history_before']}",
        f"- C overflow: dropped {tc['truncation']['dropped_messages']} msgs, "
        f"hist {tc['history_before']}→{tc['history_after']}",
        "",
        "## C answer",
        "",
        c["content"],
        "",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    print(f"  wrote {HERE / 'results.json'} and RESULTS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

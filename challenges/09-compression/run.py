#!/usr/bin/env python3
"""Challenge 09 — history compression: off vs on token/quality compare."""

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
MODEL = os.environ.get("CHALLENGE_AGENT_MODEL", "google/gemini-2.5-flash")
SYSTEM = (
    "Ты ассистент с памятью фактов. Отвечай коротко (1–3 предложения). "
    "Если спрашивают имя или язык — используй факты из диалога/сводки."
)
NAME = "Компрессия · День 9"
FACTS = [
    ("Меня зовут Артем.", "имя"),
    ("Любимый язык — Python.", "язык"),
    ("Работаю в AIChallenge.", "проект"),
    ("Любимый цвет — синий.", "цвет"),
    ("Живу в городе у моря.", "город"),
    ("Пью зелёный чай.", "чай"),
]


def _seed(base: str, draft: str, *, compress: bool) -> str | None:
    try:
        agent_dialog_clear(base, draft)
    except Exception as exc:  # noqa: BLE001
        print(f"  clear {draft}: {exc}")
    dialog_id = None
    for text, _ in FACTS:
        r = agent_run(
            base,
            f"Запомни: {text} Подтверди одним словом «ок».",
            system_prompt=SYSTEM,
            name=NAME,
            preferred_model=MODEL,
            temperature=0.2,
            max_tokens=40,
            persist=True,
            client_draft_id=draft,
            dialog_id=dialog_id,
            compress=compress,
            recent_keep=4,
            summarize_every=6,
            timeout=180.0,
        )
        dialog_id = r.get("dialog_id") or dialog_id
    return str(dialog_id) if dialog_id else None


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    print(f"==> challenge 09 compression @ {base}")

    # Off
    d_off = "challenge-09-off"
    id_off = _seed(base, d_off, compress=False)
    off = agent_run(
        base,
        "Как меня зовут и какой любимый язык? Две короткие строки: Имя: … / Язык: …",
        system_prompt=SYSTEM,
        name=NAME,
        preferred_model=MODEL,
        temperature=0.1,
        max_tokens=80,
        persist=True,
        client_draft_id=d_off,
        dialog_id=id_off,
        compress=False,
        timeout=180.0,
    )
    tok_off = (off.get("tokens") or {}).get("request")
    print(f"  OFF request_tok={tok_off} answer={off['content']!r}")

    # On
    d_on = "challenge-09-on"
    id_on = _seed(base, d_on, compress=True)
    on = agent_run(
        base,
        "Как меня зовут и какой любимый язык? Две короткие строки: Имя: … / Язык: …",
        system_prompt=SYSTEM,
        name=NAME,
        preferred_model=MODEL,
        temperature=0.1,
        max_tokens=80,
        persist=True,
        client_draft_id=d_on,
        dialog_id=id_on,
        compress=True,
        recent_keep=4,
        summarize_every=6,
        timeout=180.0,
    )
    comp = on.get("compression") or {}
    tok_on = (on.get("tokens") or {}).get("request")
    print(
        f"  ON request_tok={tok_on} raw→comp={comp.get('tokens_raw_est')}→"
        f"{comp.get('tokens_compressed_est')} refreshed={comp.get('summary_refreshed')}"
    )
    print(f"  ON answer={on['content']!r}")

    low = (on["content"] or "").lower()
    if "артем" not in low or "python" not in low:
        raise SystemExit("ON: expected Артем+Python in compressed recall")
    if not comp.get("enabled"):
        raise SystemExit("ON: missing compression block")
    if comp.get("tokens_compressed_est", 10**9) >= comp.get("tokens_raw_est", 0):
        print("  warn: compressed_est not smaller than raw (still ok if summary thin)")

    payload = {
        "challenge": "09-compression",
        "ts": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "model": MODEL,
        "off": {"tokens": off.get("tokens"), "content": off["content"]},
        "on": {
            "tokens": on.get("tokens"),
            "compression": comp,
            "content": on["content"],
        },
        "ok": True,
    }
    write_json(str(HERE / "results.json"), payload)
    md = [
        "# Challenge 09 — Compression",
        "",
        f"Prod: `{base}` · {payload['ts']}",
        "",
        f"- OFF request≈{tok_off}: {off['content']}",
        f"- ON request≈{tok_on} · raw→comp {comp.get('tokens_raw_est')}→"
        f"{comp.get('tokens_compressed_est')}",
        f"- ON answer: {on['content']}",
        "",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    print("  wrote results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

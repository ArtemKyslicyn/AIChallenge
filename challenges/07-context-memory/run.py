#!/usr/bin/env python3
"""Challenge 07 — agent dialog memory (persist → reload → continue)."""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _lib.prod_client import (  # noqa: E402
    DEFAULT_BASE,
    agent_dialog_clear,
    agent_dialog_get,
    agent_run,
    write_json,
)

HERE = Path(__file__).resolve().parent
DRAFT_ID = "challenge-07-artem"
STRONG = os.environ.get("CHALLENGE_AGENT_MODEL", "google/gemini-2.5-flash")
SYSTEM = (
    "Ты тестовый агент памяти (День 7). "
    "Кратко подтверждай факты о пользователе и используй их после «перезапуска» диалога. "
    "Когда просят формат — соблюдай его буквально."
)
NAME = "Память · Артем"


def _assert_contains(text: str, *needles: str, label: str) -> None:
    low = (text or "").lower()
    missing = [n for n in needles if n.lower() not in low]
    if missing:
        raise SystemExit(f"{label}: missing {missing!r} in {text!r}")


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    intro = (HERE / "prompt.txt").read_text(encoding="utf-8").strip()
    recall = (
        "Проверка после перезапуска. Ответь ровно двумя строками:\n"
        "Имя: <только имя>\n"
        "Язык: <только язык>"
    )
    print(f"==> challenge 07 context memory @ {base} model={STRONG}")

    try:
        agent_dialog_clear(base, DRAFT_ID)
        print("  cleared prior dialog (if any)")
    except Exception as exc:  # noqa: BLE001
        print(f"  clear skipped: {exc}")

    # --- Case A: store facts ---
    turn1 = agent_run(
        base,
        intro,
        system_prompt=SYSTEM,
        name=NAME,
        preferred_model=STRONG,
        temperature=0.2,
        max_tokens=256,
        timeout=180.0,
        persist=True,
        client_draft_id=DRAFT_ID,
    )
    dialog_id = turn1.get("dialog_id")
    print(
        f"  A store model_id={turn1['model_id']} dialog_id={dialog_id} "
        f"latency={turn1['latency_ms']}ms"
    )
    _assert_contains(turn1["content"], "Артем", "Python", label="turn1")

    stored = agent_dialog_get(base, DRAFT_ID)
    if not stored or not stored.get("messages"):
        raise SystemExit("dialog missing after persist turn1")
    n_after_1 = len(stored["messages"])
    print(f"  stored messages after A: {n_after_1}")

    # --- Case B: recall after «restart» (new request, same draft) ---
    turn2 = agent_run(
        base,
        recall,
        system_prompt=SYSTEM,
        name=NAME,
        preferred_model=STRONG,
        temperature=0.1,
        max_tokens=128,
        timeout=180.0,
        persist=True,
        client_draft_id=DRAFT_ID,
        dialog_id=str(dialog_id) if dialog_id else None,
    )
    print(f"  B recall model_id={turn2['model_id']} content={turn2['content']!r}")
    _assert_contains(turn2["content"], "Артем", "Python", label="turn2")
    if not re.search(r"имя\s*:", turn2["content"], re.I):
        raise SystemExit(f"turn2: expected 'Имя:' line in {turn2['content']!r}")
    if not re.search(r"язык\s*:", turn2["content"], re.I):
        raise SystemExit(f"turn2: expected 'Язык:' line in {turn2['content']!r}")

    after = agent_dialog_get(base, DRAFT_ID)
    n_after_2 = len((after or {}).get("messages") or [])
    print(f"  stored messages after B: {n_after_2}")

    # --- Case C: clear wipes memory ---
    agent_dialog_clear(base, DRAFT_ID)
    gone = agent_dialog_get(base, DRAFT_ID)
    n_clear = len((gone or {}).get("messages") or [])
    if n_clear != 0:
        raise SystemExit(f"clear failed — still {n_clear} messages")
    print("  C clear → 0 messages")

    turn3 = agent_run(
        base,
        "Как меня зовут? Если не знаешь — скажи «не знаю».",
        system_prompt=SYSTEM,
        name=NAME,
        preferred_model=STRONG,
        temperature=0.1,
        max_tokens=64,
        timeout=180.0,
        persist=True,
        client_draft_id=DRAFT_ID,
    )
    print(f"  C after-clear content={turn3['content']!r}")
    # Should not confidently recall Артем from wiped history
    low3 = (turn3["content"] or "").lower()
    if "артем" in low3 and "не знаю" not in low3 and "не помн" not in low3:
        print("  warn: model may have guessed name from system/user message — check UI clear demo")

    payload = {
        "challenge": "07-context-memory",
        "base_url": base,
        "ts": datetime.now(timezone.utc).isoformat(),
        "endpoint": "/api/v1/agent-workshop/run?persist=true",
        "client_draft_id": DRAFT_ID,
        "model": STRONG,
        "cases": {
            "A_store_facts": {"ok": True, "result": turn1},
            "B_recall_after_restart": {"ok": True, "result": turn2},
            "C_clear_wipes": {"messages_after_clear": n_clear, "probe": turn3},
        },
        "message_counts": {"after_A": n_after_1, "after_B": n_after_2, "after_C": n_clear},
        "memory_ok": True,
        "ui": "https://aichallenge.arcilite.ru/?shell=agents",
        "note": "Postgres agent_dialogs — Артем + Python; clear empties history.",
    }
    write_json(str(HERE / "results.json"), payload)

    md = [
        "# Challenge 07 — Context Memory (Артем)",
        "",
        f"Prod: `{base}` · {payload['ts']}",
        "",
        f"- Draft: `{DRAFT_ID}` · model: `{STRONG}`",
        "- Case A store: **Артем** + **Python**",
        "- Case B recall after restart: format `Имя:` / `Язык:` — **passed**",
        f"- Case C clear → `{n_clear}` messages",
        "",
        "## A — store",
        "",
        intro,
        "",
        turn1["content"],
        "",
        "## B — recall",
        "",
        recall,
        "",
        turn2["content"],
        "",
        "## C — after clear",
        "",
        turn3["content"],
        "",
        f"UI: {payload['ui']}",
        "",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    print(f"  wrote {HERE / 'results.json'} and RESULTS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

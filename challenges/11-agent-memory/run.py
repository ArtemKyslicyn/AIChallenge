#!/usr/bin/env python3
"""Challenge 11 — three-layer agent memory (short / working / long-term)."""

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
    agent_memory_get,
    agent_memory_write,
    agent_run,
    write_json,
)

HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("CHALLENGE_AGENT_MODEL", "google/gemini-2.5-flash")
SYSTEM = (
    "Ты помощник по задачам. Отвечай коротко (1–3 предложения). "
    "Если в system есть блоки памяти — опирайся на них явно: "
    "зови пользователя по имени из профиля, повторяй цель из рабочей памяти."
)
NAME = "Память · День 11"
DRAFT = "challenge-11-memory"


def _probe(base: str, dialog_id: str | None, message: str) -> dict:
    return agent_run(
        base,
        message,
        system_prompt=SYSTEM,
        name=NAME,
        preferred_model=MODEL,
        temperature=0.1,
        max_tokens=120,
        persist=True,
        client_draft_id=DRAFT,
        dialog_id=dialog_id,
        timeout=180.0,
    )


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    print(f"==> challenge 11 agent memory @ {base}")

    try:
        agent_dialog_clear(base, DRAFT)
    except Exception as exc:  # noqa: BLE001
        print(f"  clear: {exc}")

    # Long-term (visitor-scoped) — explicit write
    agent_memory_write(
        base,
        layer="long_term",
        kind="profile",
        key="name",
        value="Артём",
        client_draft_id=DRAFT,
    )
    agent_memory_write(
        base,
        layer="long_term",
        kind="decision",
        value="Стек: FastAPI + React + Postgres",
        client_draft_id=DRAFT,
    )
    agent_memory_write(
        base,
        layer="long_term",
        kind="knowledge",
        key="domain",
        value="AIChallenge — чат-платформа, без медицинской терминологии",
        client_draft_id=DRAFT,
    )

    # Short-term seed turn (creates dialog)
    seed = _probe(base, None, "Привет. Сегодня собираем демо памяти агента.")
    dialog_id = seed.get("dialog_id")

    # Working memory — explicit write (dialog-scoped)
    agent_memory_write(
        base,
        layer="working",
        kind="goal",
        value="Показать три слоя памяти в ответе агента",
        client_draft_id=DRAFT,
    )
    agent_memory_write(
        base,
        layer="working",
        kind="checklist_item",
        value="Проверить, что имя берётся из long-term",
        client_draft_id=DRAFT,
    )
    agent_memory_write(
        base,
        layer="working",
        kind="checklist_item",
        value="Проверить, что цель берётся из working",
        client_draft_id=DRAFT,
    )

    snap = agent_memory_get(base, DRAFT)
    working = snap.get("working") or {}
    long_term = snap.get("long_term") or {}
    short_n = len(snap.get("short_term") or [])

    print(f"  layers: short={short_n} working.goal={working.get('goal')!r}")
    print(f"  long_term.profile={long_term.get('profile')}")

    with_mem = _probe(
        base,
        dialog_id,
        "Кто я и какая сейчас цель задачи? Ответь двумя строками: "
        "Имя: … / Цель: …",
    )
    dialog_id = with_mem.get("dialog_id") or dialog_id
    answer_with = str(with_mem.get("content") or "")
    print(f"  with memory: {answer_with!r}")

    # Control: same question after clearing working (long-term stays)
    try:
        agent_dialog_clear(base, DRAFT)
    except Exception as exc:  # noqa: BLE001
        print(f"  clear2: {exc}")

    # Re-seed short-term only; do not rewrite working
    seed2 = _probe(base, None, "Новый диалог без рабочей цели.")
    dialog_id2 = seed2.get("dialog_id")
    without_working = _probe(
        base,
        dialog_id2,
        "Кто я и какая сейчас цель задачи? Ответь двумя строками: "
        "Имя: … / Цель: …",
    )
    answer_without = str(without_working.get("content") or "")
    print(f"  without working: {answer_without!r}")

    snap_after = agent_memory_get(base, DRAFT)
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base": base,
        "model": with_mem.get("model_id"),
        "layers_before_probe": {
            "short_term_count": short_n,
            "working": working,
            "long_term": long_term,
        },
        "answer_with_all_layers": answer_with,
        "answer_after_clear_working": answer_without,
        "layers_after_clear": {
            "short_term_count": len(snap_after.get("short_term") or []),
            "working": snap_after.get("working") or {},
            "long_term": snap_after.get("long_term") or {},
        },
        "checks": {
            "name_in_with": "артём" in answer_with.lower() or "артем" in answer_with.lower(),
            "goal_in_with": "три слоя" in answer_with.lower() or "памят" in answer_with.lower(),
            "name_survives_clear": "артём" in answer_without.lower()
            or "артем" in answer_without.lower(),
            "working_cleared": not bool((snap_after.get("working") or {}).get("goal")),
        },
    }

    write_json(str(HERE / "results.json"), results)
    lines = [
        "# Challenge 11 — Agent Memory",
        "",
        f"Prod: `{base}` · {results['generated_at']}",
        "",
        "## Слои до пробы",
        f"- short_term: {short_n} реплик",
        f"- working.goal: {working.get('goal')}",
        f"- long_term.profile: {long_term.get('profile')}",
        "",
        "## Ответ с памятью",
        f"- {answer_with}",
        "",
        "## После clear dialog (working сброшен, long-term жив)",
        f"- {answer_without}",
        "",
        "## Checks",
    ]
    for k, v in results["checks"].items():
        lines.append(f"- {k}: {'OK' if v else 'FAIL'}")
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  wrote RESULTS.md / results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

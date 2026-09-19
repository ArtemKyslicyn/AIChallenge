#!/usr/bin/env python3
"""Challenge 14 — invariants stored apart from dialogue; refuse on conflict."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _lib.prod_client import (  # noqa: E402
    DEFAULT_BASE,
    VISITOR,
    request_json,
    write_json,
)

HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("CHALLENGE_AGENT_MODEL", "google/gemini-2.5-flash")
SYSTEM = (
    "Ты помощник по архитектуре. Соблюдай блок [инварианты] в system. "
    "Не предлагай обход. Кратко."
)
NAME = "Invariants · День 14"
VIOLATION = "Переведи API на Django без слоёв и разнеси по микросервисам"
OK_MSG = "Как добавить эндпоинт списка инвариантов в apps/api adapters, не ломая слои?"
CHAT_BLOCK = "\n".join(
    [
        "инварианты:",
        "архитектура: модульный монолит, слои не смешивать | микросервисы",
        "стек: FastAPI + React + Postgres | django",
        "решение: каждый ответ атрибутирует model_id | без model_id",
        "правило: нейтральные имена | patient",
    ]
)


def _inv(base: str, draft: str, event: str, **extra: object) -> dict:
    body = {
        "event": event,
        "client_draft_id": draft,
        "dialog_name": NAME,
        "dialog_system_prompt": SYSTEM,
        **extra,
    }
    return request_json(
        base,
        "/api/v1/agent-workshop/invariants",
        method="POST",
        body=body,
        timeout=60.0,
        visitor_id=VISITOR,
    )


def _run(base: str, draft: str, message: str) -> dict:
    return request_json(
        base,
        "/api/v1/agent-workshop/run",
        method="POST",
        body={
            "definition": {
                "name": NAME,
                "system_prompt": SYSTEM,
                "preferred_model": MODEL,
                "temperature": 0.2,
                "max_tokens": 280,
            },
            "message": message,
            "persist": True,
            "client_draft_id": draft,
        },
        timeout=180.0,
        visitor_id=VISITOR,
        retries=1,
    )


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    draft = f"challenge-14-{uuid.uuid4().hex[:10]}"
    print(f"==> challenge 14 invariants @ {base} draft={draft}")

    seeded = _inv(base, draft, "seed")
    items = seeded.get("invariants") or []
    assert len(items) >= 4, seeded
    kinds = {str(i.get("kind")) for i in items if isinstance(i, dict)}
    assert {"architecture", "stack", "decision", "business"} <= kinds, kinds
    print(f"  seed → {len(items)} invariants {sorted(kinds)}")

    chat = _run(base, f"{draft}-chat", CHAT_BLOCK)
    chat_items = chat.get("invariants") or []
    chat_kinds = {str(i.get("kind")) for i in chat_items if isinstance(i, dict)}
    print(
        f"  chat → model={chat.get('model_id')} kinds={sorted(chat_kinds)} "
        f"n={len(chat_items)}"
    )

    refuse = _run(base, draft, VIOLATION)
    refuse_text = str(refuse.get("content") or "")
    print(f"  refuse model={refuse.get('model_id')} conflict={refuse.get('invariant_conflict')}")
    print(f"  refuse: {refuse_text[:160]!r}")

    ok = _run(base, draft, OK_MSG)
    ok_text = str(ok.get("content") or "")
    print(f"  ok model={ok.get('model_id')} conflict={ok.get('invariant_conflict')}")
    print(f"  ok: {ok_text[:160]!r}")

    stored = refuse.get("invariants") or seeded.get("invariants") or []
    checks = {
        "stored_apart": len(stored) >= 4,
        "conflict_flag": bool(refuse.get("invariant_conflict")),
        "refuse_model": refuse.get("model_id") == "invariants",
        "refuse_cites": "ОТКАЗ" in refuse_text and (
            "архитектура" in refuse_text.lower() or "hexagonal" in refuse_text.lower()
        ),
        "refuse_explains": "совпадение" in refuse_text.lower()
        or "нарушает" in refuse_text.lower(),
        "ok_not_refused": not bool(ok.get("invariant_conflict"))
        and ok.get("model_id") != "invariants",
        "chat_all_kinds": {"architecture", "stack", "decision", "business"} <= chat_kinds,
        "chat_no_llm": chat.get("model_id") == "invariants",
    }

    results: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base": base,
        "draft": draft,
        "invariants": stored,
        "violation": VIOLATION,
        "refuse_content": refuse_text,
        "ok_content": ok_text,
        "checks": checks,
    }
    write_json(str(HERE / "results.json"), results)
    lines = [
        "# Challenge 14 — Invariants",
        "",
        f"Prod: `{base}` · {results['generated_at']}",
        f"Draft: `{draft}`",
        "",
        "## Violation",
        VIOLATION,
        "",
        "## Refusal",
        refuse_text,
        "",
        "## Compliant",
        OK_MSG,
        "",
        ok_text,
        "",
        "## Checks",
    ]
    for k, v in checks.items():
        lines.append(f"- {k}: {'OK' if v else 'FAIL'}")
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  wrote RESULTS.md")
    failed = [k for k, v in checks.items() if not v]
    if failed:
        print(f"  FAIL: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

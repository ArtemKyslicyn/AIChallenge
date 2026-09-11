#!/usr/bin/env python3
"""Challenge 10 — compare sliding / facts / compress / branching on one TZ scenario."""

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
    agent_dialog_fork,
    agent_run,
    write_json,
)

HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("CHALLENGE_AGENT_MODEL", "google/gemini-2.5-flash")
SYSTEM = (
    "Ты помощник по сбору ТЗ. Отвечай коротко (1–3 предложения). "
    "Запоминай цель, стек, ограничения. При вопросе — опирайся на контекст."
)
NAME = "Стратегии · День 10"
SCRIPT = [
    "Цель продукта: чат-платформа для AIChallenge.",
    "Стек: FastAPI + React + Postgres.",
    "Ограничение: анонимные сессии, без медицинской терминологии.",
    "Дедлайн демо: две недели.",
    "Предпочтение: SSE стриминг ответов.",
    "Решение: хранить диалоги агента в Postgres.",
    "Договорённость: каждый ответ показывает model_id.",
    "Ещё ограничение: не трогать Reality/xray при деплое.",
]


def _seed(base: str, draft: str, *, mode: str) -> str | None:
    try:
        agent_dialog_clear(base, draft)
    except Exception as exc:  # noqa: BLE001
        print(f"  clear {draft}: {exc}")
    dialog_id = None
    for i, text in enumerate(SCRIPT, start=1):
        r = agent_run(
            base,
            f"Факт {i}: {text} Подтверди «ок».",
            system_prompt=SYSTEM,
            name=NAME,
            preferred_model=MODEL,
            temperature=0.2,
            max_tokens=40,
            persist=True,
            client_draft_id=draft,
            dialog_id=dialog_id,
            context_mode=mode,
            recent_keep=4,
            summarize_every=6,
            timeout=180.0,
        )
        dialog_id = r.get("dialog_id") or dialog_id
    return str(dialog_id) if dialog_id else None


def _probe(base: str, draft: str, dialog_id: str | None, mode: str) -> dict:
    return agent_run(
        base,
        "Кратко: какая цель и какой стек? Две строки: Цель: … / Стек: …",
        system_prompt=SYSTEM,
        name=NAME,
        preferred_model=MODEL,
        temperature=0.1,
        max_tokens=100,
        persist=True,
        client_draft_id=draft,
        dialog_id=dialog_id,
        context_mode=mode,
        recent_keep=4,
        summarize_every=6,
        timeout=180.0,
    )


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    print(f"==> challenge 10 context strategies @ {base}")
    results: dict[str, object] = {}

    for mode in ("sliding", "facts", "compress"):
        draft = f"challenge-10-{mode}"
        did = _seed(base, draft, mode=mode)
        out = _probe(base, draft, did, mode)
        strat = out.get("context_strategy") or {}
        tok = (out.get("tokens") or {}).get("request")
        print(f"  {mode}: req≈{tok} strat={strat.get('tokens_raw_est')}→{strat.get('tokens_strategy_est')}")
        print(f"    answer={out['content']!r}")
        results[mode] = {
            "tokens": out.get("tokens"),
            "context_strategy": strat,
            "content": out["content"],
        }

    # Branching: seed none, fork at mid, diverge
    draft = "challenge-10-branch-root"
    did = _seed(base, draft, mode="none")
    root = agent_run(
        base,
        "Сводка: повтори цель одним словом-фразой.",
        system_prompt=SYSTEM,
        name=NAME,
        preferred_model=MODEL,
        temperature=0.1,
        max_tokens=40,
        persist=True,
        client_draft_id=draft,
        dialog_id=did,
        context_mode="none",
        timeout=180.0,
    )
    msgs = root.get("messages") or []
    checkpoint = None
    for m in msgs:
        if m.get("role") == "user" and "Факт 4" in str(m.get("content") or ""):
            checkpoint = m.get("id")
            break
    if not checkpoint and msgs:
        checkpoint = msgs[min(7, len(msgs) - 1)].get("id")
    if not checkpoint or not root.get("dialog_id"):
        raise SystemExit("branch: missing checkpoint")

    a = agent_dialog_fork(
        base,
        str(root["dialog_id"]),
        from_message_id=str(checkpoint),
        client_draft_id="challenge-10-branch-a",
        label="A-mobile",
    )
    b = agent_dialog_fork(
        base,
        str(root["dialog_id"]),
        from_message_id=str(checkpoint),
        client_draft_id="challenge-10-branch-b",
        label="B-desktop",
    )
    ra = agent_run(
        base,
        "В этой ветке приоритет — мобильный UI. Запомни. Какой приоритет?",
        system_prompt=SYSTEM,
        name=NAME,
        preferred_model=MODEL,
        persist=True,
        client_draft_id="challenge-10-branch-a",
        dialog_id=a.get("id"),
        context_mode="none",
        max_tokens=60,
        timeout=180.0,
    )
    rb = agent_run(
        base,
        "В этой ветке приоритет — desktop analytics. Запомни. Какой приоритет?",
        system_prompt=SYSTEM,
        name=NAME,
        preferred_model=MODEL,
        persist=True,
        client_draft_id="challenge-10-branch-b",
        dialog_id=b.get("id"),
        context_mode="none",
        max_tokens=60,
        timeout=180.0,
    )
    print(f"  branch A: {ra['content']!r}")
    print(f"  branch B: {rb['content']!r}")
    results["branching"] = {
        "a": ra["content"],
        "b": rb["content"],
        "checkpoint": checkpoint,
    }

    payload = {
        "challenge": "10-context-strategies",
        "ts": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "model": MODEL,
        "results": results,
        "ok": True,
    }
    write_json(str(HERE / "results.json"), payload)
    lines = [
        "# Challenge 10 — Context Strategies",
        "",
        f"Prod: `{base}` · {payload['ts']}",
        "",
    ]
    for mode in ("sliding", "facts", "compress"):
        block = results[mode]  # type: ignore[index]
        lines.append(f"## {mode}")
        lines.append(f"- {block['content']}")  # type: ignore[index]
        lines.append("")
    lines.append("## branching")
    lines.append(f"- A: {ra['content']}")
    lines.append(f"- B: {rb['content']}")
    lines.append("")
    (HERE / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    print("  wrote results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

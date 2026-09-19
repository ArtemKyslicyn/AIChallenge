#!/usr/bin/env python3
"""Challenge 15 — explicit transition graph; refuse skips; pause keeps stage."""

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
    "Ты помощник по задачам. Соблюдай блок [задача] и граф переходов. "
    "Не перескакивай этапы. После resume не пересказывай план. Кратко."
)
NAME = "Task transitions · День 15"
GOAL = "Подготовить чеклист контролируемых переходов задачи"
SKIP_IMPL = "пиши код модуля авторизации прямо сейчас"
SKIP_FINALE = "сразу финал, закрой задачу без проверки"
SKIP_PAUSED = "пиши код дальше по шагам"


def _task(base: str, draft: str, event: str, **extra: object) -> dict:
    body = {
        "event": event,
        "client_draft_id": draft,
        "dialog_name": NAME,
        "dialog_system_prompt": SYSTEM,
        **extra,
    }
    return request_json(
        base,
        "/api/v1/agent-workshop/task",
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


def _expect_http(fn, *, code: int) -> str:
    try:
        fn()
    except RuntimeError as exc:
        text = str(exc)
        if f"HTTP {code}" in text:
            return text
        raise
    raise AssertionError(f"expected HTTP {code}")


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    draft = f"challenge-15-{uuid.uuid4().hex[:10]}"
    print(f"==> challenge 15 task-transitions @ {base} draft={draft}")

    start = _task(base, draft, "start", goal=GOAL)
    task = start.get("task") or {}
    assert task.get("stage") == "planning", start
    assert task.get("allowed_next") == ["execution"], start

    illegal = _expect_http(
        lambda: _task(base, draft, "goto", stage="done"),
        code=422,
    )
    print(f"  illegal goto: {illegal[:160]!r}")

    skip_impl = _run(base, draft, SKIP_IMPL)
    skip_impl_text = str(skip_impl.get("content") or "")
    assert skip_impl.get("task_skip_conflict") is True, skip_impl
    assert skip_impl.get("model_id") == "task-fsm", skip_impl
    assert "план" in skip_impl_text.lower(), skip_impl_text
    print(f"  skip impl: {skip_impl_text[:120]!r}")

    goto_exec = _task(base, draft, "goto", stage="execution")
    assert goto_exec.get("task", {}).get("stage") == "execution", goto_exec
    assert goto_exec.get("task", {}).get("allowed_next") == ["validation"], goto_exec

    skip_fin = _run(base, draft, SKIP_FINALE)
    skip_fin_text = str(skip_fin.get("content") or "")
    assert skip_fin.get("task_skip_conflict") is True, skip_fin
    assert "валидац" in skip_fin_text.lower(), skip_fin_text
    print(f"  skip finale: {skip_fin_text[:120]!r}")

    paused = _task(base, draft, "pause")
    assert paused.get("task", {}).get("paused") is True, paused
    assert paused.get("task", {}).get("stage") == "execution", paused
    assert paused.get("task", {}).get("allowed_next") == [], paused

    skip_pause = _run(base, draft, SKIP_PAUSED)
    skip_pause_text = str(skip_pause.get("content") or "")
    assert skip_pause.get("task_skip_conflict") is True, skip_pause
    assert "пауз" in skip_pause_text.lower(), skip_pause_text

    resumed = _task(base, draft, "resume")
    assert resumed.get("task", {}).get("paused") is False, resumed
    assert resumed.get("task", {}).get("stage") == "execution", resumed

    cont = _run(base, draft, "продолжи")
    cont_text = str(cont.get("content") or "")
    print(f"  resume reply: {cont_text[:120]!r}")

    to_val = _task(base, draft, "advance")
    assert to_val.get("task", {}).get("stage") == "validation", to_val
    to_done = _task(base, draft, "advance")
    assert to_done.get("task", {}).get("stage") == "done", to_done

    results: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base": base,
        "draft": draft,
        "illegal_goto": illegal[:400],
        "skip_implementation": skip_impl_text,
        "skip_finale": skip_fin_text,
        "skip_paused": skip_pause_text,
        "resume_content": cont_text,
        "checks": {
            "graph_planning_to_execution_only": task.get("allowed_next") == ["execution"],
            "illegal_goto_done_rejected": "граф" in illegal.lower()
            or "недопустим" in illegal.lower()
            or "нельзя" in illegal.lower(),
            "refuse_impl_before_plan": skip_impl.get("task_skip_conflict") is True,
            "refuse_finale_without_validation": skip_fin.get("task_skip_conflict") is True,
            "pause_clears_allowed_next": paused.get("task", {}).get("allowed_next") == [],
            "resume_keeps_execution": resumed.get("task", {}).get("stage") == "execution",
            "reached_done": to_done.get("task", {}).get("stage") == "done",
        },
    }
    write_json(str(HERE / "results.json"), results)
    lines = [
        "# Challenge 15 — Task transitions",
        "",
        f"Prod: `{base}` · {results['generated_at']}",
        f"Draft: `{draft}`",
        "",
        "## Skip implementation",
        skip_impl_text,
        "",
        "## Skip finale",
        skip_fin_text,
        "",
        "## Checks",
    ]
    for k, v in results["checks"].items():  # type: ignore[union-attr]
        lines.append(f"- {k}: {'OK' if v else 'FAIL'}")
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  wrote RESULTS.md")
    failed = [k for k, v in results["checks"].items() if not v]  # type: ignore[union-attr]
    if failed:
        print(f"  FAIL: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

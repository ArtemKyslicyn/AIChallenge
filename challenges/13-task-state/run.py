#!/usr/bin/env python3
"""Challenge 13 — task FSM: advance, pause, resume without re-briefing."""

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
    "Ты помощник по задачам. Соблюдай блок [задача] в system. "
    "После resume не пересказывай план — продолжай текущий шаг. Кратко."
)
NAME = "Task FSM · День 13"
GOAL = (
    "Подготовить короткий чеклист запуска фичи Task State: "
    "1) описать этапы 2) проверить паузу 3) проверить resume"
)


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


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    draft = f"challenge-13-{uuid.uuid4().hex[:10]}"
    print(f"==> challenge 13 task-state @ {base} draft={draft}")

    start = _task(base, draft, "start", goal=GOAL)
    assert start.get("task", {}).get("stage") == "planning", start
    print(f"  start → {start.get('task')}")

    plan = _run(base, draft, "Кратко: что сделаешь на этапе planning?")
    plan_text = str(plan.get("content") or "")
    print(f"  planning reply: {plan_text[:100]!r}")

    adv = _task(base, draft, "advance")
    assert adv.get("task", {}).get("stage") == "execution", adv
    print(f"  advance → {adv.get('task')}")

    paused = _task(base, draft, "pause")
    assert paused.get("task", {}).get("paused") is True, paused
    brief = str(paused.get("task", {}).get("resume_brief") or "")
    print(f"  pause brief: {brief[:120]!r}")

    resumed = _task(base, draft, "resume")
    assert resumed.get("task", {}).get("paused") is False, resumed
    assert resumed.get("task", {}).get("stage") == "execution", resumed

    cont = _run(base, draft, "продолжи")
    cont_text = str(cont.get("content") or "")
    print(f"  resume reply: {cont_text[:120]!r}")

    goal_chunk = GOAL[:40].lower()
    rebrief = cont_text.lower().count(goal_chunk) > 0 and len(cont_text) > 600
    looks_like_full_plan = (
        cont_text.lower().startswith("план") and "1)" in cont_text and "2)" in cont_text
    )

    done = _task(base, draft, "advance")
    assert done.get("task", {}).get("stage") == "validation", done
    done2 = _task(base, draft, "advance")
    assert done2.get("task", {}).get("stage") == "done", done2

    results: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base": base,
        "draft": draft,
        "stages": {
            "after_start": start.get("task"),
            "after_advance": adv.get("task"),
            "after_pause": paused.get("task"),
            "after_resume": resumed.get("task"),
            "done": done2.get("task"),
        },
        "planning_content": plan_text,
        "resume_content": cont_text,
        "checks": {
            "pause_mid_execution": paused.get("task", {}).get("stage") == "execution"
            and paused.get("task", {}).get("paused") is True,
            "resume_keeps_stage": resumed.get("task", {}).get("stage") == "execution",
            "no_heavy_rebrief": not rebrief and not looks_like_full_plan,
            "reached_done": done2.get("task", {}).get("stage") == "done",
        },
    }
    write_json(str(HERE / "results.json"), results)
    lines = [
        "# Challenge 13 — Task State",
        "",
        f"Prod: `{base}` · {results['generated_at']}",
        f"Draft: `{draft}`",
        "",
        "## Resume reply",
        cont_text,
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

#!/usr/bin/env python3
"""Run Day-25 scenarios against a live API (prod or local).

Usage:
  BASE_URL=https://aichallenge.arcilite.ru/api/v1 \\
  python challenges/25-rag-memory/run.py --scenario a --limit 6
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = Path(__file__).with_name("SCENARIOS.md")

DEFINITION = {
    "name": "База + память",
    "system_prompt": (
        "Ты ассистент стенда AIChallenge с доступом к базе знаний (RAG). "
        "Отвечай по найденным фрагментам и памяти задачи. Не выдумывай порты."
    ),
    "preferred_model": "auto",
    "temperature": 0.3,
    "max_tokens": 700,
}


def _lines_for(scenario: str) -> list[str]:
    text = SCENARIOS.read_text(encoding="utf-8")
    key = "Сценарий A" if scenario == "a" else "Сценарий B"
    chunk = text.split(key, 1)[1]
    chunk = chunk.split("## Сценарий", 1)[0]
    out: list[str] = []
    for line in chunk.splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        # "1. question"
        q = line.split(".", 1)[1].strip()
        if q:
            out.append(q)
    return out


def _request(base: str, path: str, payload: dict, visitor: str, *, attempts: int = 3) -> dict:
    data = json.dumps(payload).encode("utf-8")
    last: Exception | None = None
    for i in range(1, attempts + 1):
        req = urllib.request.Request(
            f"{base.rstrip('/')}{path}",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Visitor-Id": visitor,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read()[:200]
            # Free-tier LLM flakes: retry transient upstream failures.
            if exc.code in {400, 429, 500, 502, 503, 504} and i < attempts:
                print(f"retry {i}/{attempts} http {exc.code}: {body!r}", file=sys.stderr)
                time.sleep(2.0 * i)
                last = exc
                continue
            print(f"FAIL http {exc.code}: {body!r}", file=sys.stderr)
            raise
        except urllib.error.URLError as exc:
            if i < attempts:
                print(f"retry {i}/{attempts} url: {exc}", file=sys.stderr)
                time.sleep(2.0 * i)
                last = exc
                continue
            raise
    assert last is not None
    raise last


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("a", "b"), default="a")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument(
        "--base",
        default=os.environ.get("BASE_URL", "https://aichallenge.arcilite.ru/api/v1"),
    )
    args = parser.parse_args()
    visitor = str(uuid.uuid4())
    draft = f"rag-memory-run-{args.scenario}"
    questions = _lines_for(args.scenario)[: max(1, args.limit)]

    print(f"base={args.base} scenario={args.scenario} turns={len(questions)}")
    _request(
        args.base,
        "/agent-workshop/task",
        {
            "event": "start",
            "client_draft_id": draft,
            "goal": "Длинный сценарий day-25: держать цель и источники.",
            "step": "ответы с RAG",
            "expected_action": "sources every turn",
            "dialog_name": DEFINITION["name"],
            "dialog_system_prompt": DEFINITION["system_prompt"],
        },
        visitor,
    )

    ok_sources = 0
    for i, q in enumerate(questions, start=1):
        try:
            body = _request(
                args.base,
                "/agent-workshop/run",
                {
                    "definition": DEFINITION,
                    "message": q,
                    "persist": True,
                    "client_draft_id": draft,
                    "context_mode": "facts",
                    "use_rag": True,
                    "rag_mode": "full",
                    "rag_top_k": 6,
                },
                visitor,
            )
        except urllib.error.HTTPError as exc:
            print(f"{i}. FAIL http {exc.code}", file=sys.stderr)
            return 1
        except urllib.error.URLError as exc:
            print(f"{i}. FAIL url: {exc}", file=sys.stderr)
            return 1
        sources = body.get("rag_sources") or []
        model = body.get("model_id")
        if sources:
            ok_sources += 1
        print(
            f"{i}. sources={len(sources)} model={model} "
            f"answer={(body.get('content') or '')[:80]!r}"
        )

    print(f"DONE turns={len(questions)} with_sources={ok_sources}")
    return 0 if ok_sources >= max(1, len(questions) // 2) else 2


if __name__ == "__main__":
    raise SystemExit(main())

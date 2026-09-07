#!/usr/bin/env python3
"""Challenge 06 — first encapsulated agent against prod agent-workshop API."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _lib.prod_client import DEFAULT_BASE, agent_run, write_json  # noqa: E402

HERE = Path(__file__).resolve().parent

SYSTEM = (
    "Ты краткий редактор текста. Правишь стиль и ясность, не меняя смысл. "
    "Отвечай только отредактированным текстом без предисловий."
)


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    prompt = (HERE / "prompt.txt").read_text(encoding="utf-8").strip()
    print(f"==> challenge 06 first agent @ {base}")

    result = agent_run(
        base,
        prompt,
        system_prompt=SYSTEM,
        name="Краткий редактор",
        preferred_model="auto",
        temperature=0.3,
        max_tokens=512,
        timeout=180.0,
    )
    print(
        f"  model_id={result['model_id']} latency={result['latency_ms']}ms "
        f"tokens≈{result['tokens_approx']} cost≈{result['cost_proxy']}"
    )

    payload = {
        "challenge": "06-first-agent",
        "base_url": base,
        "ts": datetime.now(timezone.utc).isoformat(),
        "endpoint": "/api/v1/agent-workshop/run",
        "definition": {
            "name": "Краткий редактор",
            "system_prompt": SYSTEM,
            "preferred_model": "auto",
            "temperature": 0.3,
            "max_tokens": 512,
        },
        "message": prompt,
        "result": result,
        "ui": "https://aichallenge.arcilite.ru/?shell=agents",
        "note": "Encapsulated agent run — not /llm/complete and not Session chat.",
    }
    write_json(str(HERE / "results.json"), payload)

    md = [
        "# Challenge 06 — First Agent",
        "",
        f"Prod: `{base}` · {payload['ts']}",
        "",
        f"- Endpoint: `{payload['endpoint']}`",
        f"- `model_id`: `{result['model_id']}`",
        f"- latency: {result['latency_ms']} ms",
        f"- tokens≈: {result['tokens_approx']}",
        f"- cost≈: {result['cost_proxy']}",
        "",
        "## Message",
        "",
        prompt,
        "",
        "## Answer",
        "",
        result["content"],
        "",
        f"UI: {payload['ui']}",
        "",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    print(f"  wrote {HERE / 'results.json'} and RESULTS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

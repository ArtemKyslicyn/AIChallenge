#!/usr/bin/env python3
"""Challenge 06 — first encapsulated agent (persona cast / strong model)."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _lib.prod_client import DEFAULT_BASE, agent_run, write_json  # noqa: E402

HERE = Path(__file__).resolve().parent
STRONG = os.environ.get("CHALLENGE_AGENT_MODEL", "google/gemini-2.5-flash")
SYSTEM = (
    "Ты Аристотель. Говоришь торжественно, ясно, через причины и категории. "
    "Теорию струн объясняй просто, без псевдонауки. 3–5 предложений, оставайся в роли."
)


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    prompt = (HERE / "prompt.txt").read_text(encoding="utf-8").strip()
    print(f"==> challenge 06 first agent @ {base} model={STRONG}")

    result = agent_run(
        base,
        "В трёх предложениях объясни теорию струн так, будто слушатель умный, но не физик.",
        system_prompt=SYSTEM,
        name="Аристотель",
        preferred_model=STRONG,
        temperature=0.5,
        max_tokens=500,
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
            "name": "Аристотель",
            "system_prompt": SYSTEM,
            "preferred_model": STRONG,
            "temperature": 0.5,
            "max_tokens": 500,
        },
        "cast": ["Алкаш", "Аристотель", "Программист"],
        "topic": prompt,
        "result": result,
        "ui": "https://aichallenge.arcilite.ru/?shell=agents",
        "note": "Encapsulated agent — string-theory persona cast on strong model.",
    }
    write_json(str(HERE / "results.json"), payload)

    md = [
        "# Challenge 06 — First Agent (теория струн)",
        "",
        f"Prod: `{base}` · {payload['ts']}",
        "",
        f"- Cast: Алкаш · Аристотель · Программист",
        f"- Solo probe: **Аристотель** @ `{STRONG}`",
        f"- `model_id`: `{result['model_id']}`",
        f"- latency: {result['latency_ms']} ms",
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

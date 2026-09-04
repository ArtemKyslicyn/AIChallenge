#!/usr/bin/env python3
"""Challenge 04 — temperature 0 / 0.7 / 1.2 against prod ×T-equivalent probes."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _lib.prod_client import DEFAULT_BASE, probe, write_json  # noqa: E402

HERE = Path(__file__).resolve().parent
TEMPS = [0.0, 0.7, 1.2]
SLOT_IDS = ["t0", "t07", "t12"]
HINTS = {
    "t0": "Факты, код, инструкции — важна повторяемость.",
    "t07": "Обычный диалог и объяснения — баланс ясности и живости.",
    "t12": "Мозговой штурм и варианты — когда нужны идеи.",
}


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    prompt = (HERE / "prompt.txt").read_text(encoding="utf-8").strip()
    # Prefer stable chat models (avoid free-pool remaps / safety stubs).
    models = [
        m.strip()
        for m in os.environ.get(
            "CHALLENGE_MODELS",
            "google/gemini-2.5-flash,deepseek/deepseek-chat,mistralai/mistral-nemo",
        ).split(",")
        if m.strip()
    ]
    print(f"==> challenge 04 temperature @ {base} models={models}")

    runs = []
    for slot, temp in zip(SLOT_IDS, TEMPS, strict=True):
        print(f"  probing t={temp} …", flush=True)
        result = probe(
            base,
            prompt,
            models=models,
            temperature=temp,
            reasoning=False,
            timeout=180.0,
        )
        runs.append(
            {
                "id": slot,
                "temperature": temp,
                **result,
                "best_for_hint": HINTS[slot],
            }
        )
        print(
            f"    model={result['model_id']} latency={result['latency_ms']}ms "
            f"tokens≈{result['tokens_approx']}"
        )

    # Local Day-4 style summary (no extra judge call — keeps the run cheap/stable).
    summary_lines = [
        "При t=0 ответы обычно суше и стабильнее (точность / инструкции).",
        "При t=0.7 — баланс ясности и живости для объяснений.",
        "При t=1.2 — больше лексического и стилевого разнообразия (креатив).",
        "Сравни примеры ниже и выбери температуру под задачу.",
    ]

    payload = {
        "challenge": "04-temperature",
        "base_url": base,
        "prompt": prompt,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
        "summary": " ".join(summary_lines),
        "ui": "https://aichallenge.arcilite.ru/ — режим ×T, пресет «Урок: 0 · 0.7 · 1.2»",
    }
    write_json(str(HERE / "results.json"), payload)

    md = [
        "# Challenge 04 — Температура",
        "",
        f"Prod: `{base}` · {payload['exported_at']}",
        "",
        "## Запрос",
        "",
        prompt,
        "",
        "## Сравнение",
        "",
        "| t | model_id | latency | tokens≈ | cost≈ |",
        "|---|----------|---------|---------|-------|",
    ]
    for r in runs:
        md.append(
            f"| {r['temperature']} | `{r['model_id']}` | {r['latency_ms']} ms | "
            f"{r['tokens_approx']} | {r['cost_proxy']} |"
        )
    md.extend(["", "## Примеры ответов", ""])
    for r in runs:
        md.append(f"### t = {r['temperature']} (`{r['model_id']}`)")
        md.append("")
        md.append(r["content"].strip() or "_(пусто)_")
        md.append("")
        md.append(f"_Лучше для:_ {r['best_for_hint']}")
        md.append("")
    md.extend(["## Вывод", "", payload["summary"], "", f"UI: {payload['ui']}", ""])
    (HERE / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {HERE / 'results.json'} and {HERE / 'RESULTS.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

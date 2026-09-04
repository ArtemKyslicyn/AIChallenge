#!/usr/bin/env python3
"""Challenge 05 — weak / mid / strong models against prod Performance Studio picks."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _lib.prod_client import (  # noqa: E402
    DEFAULT_BASE,
    list_models,
    pick_tiers,
    probe,
    write_json,
)

HERE = Path(__file__).resolve().parent
TIER_ORDER = ["weak", "mid", "strong"]
TIER_LABEL = {"weak": "Слабая", "mid": "Средняя", "strong": "Сильная"}


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    prompt = (HERE / "prompt.txt").read_text(encoding="utf-8").strip()
    print(f"==> challenge 05 model tiers @ {base}")

    catalog = list_models(base)
    ids = [str(m.get("id") or "") for m in catalog]
    picks = pick_tiers(ids)
    print(f"  catalog={len(ids)} picks={picks}")

    runs = []
    for tier in TIER_ORDER:
        model = picks[tier]
        print(f"  probing {tier}={model} …", flush=True)
        # Fallbacks if the catalog pick remaps to a broken free stub.
        fallbacks = [model, "google/gemini-2.5-flash", "deepseek/deepseek-chat", "mistralai/mistral-nemo"]
        # unique preserve order
        seen: set[str] = set()
        models = []
        for m in fallbacks:
            if m and m not in seen:
                seen.add(m)
                models.append(m)
        result = probe(
            base,
            prompt,
            models=models,
            temperature=0.7,
            reasoning=False,
            timeout=180.0,
        )
        runs.append({"tier": tier, "requested_model": model, **result})
        print(
            f"    resolved={result['model_id']} latency={result['latency_ms']}ms "
            f"tokens≈{result['tokens_approx']} cost≈{result['cost_proxy']}"
        )

    # Rank for short conclusion
    by_latency = sorted(runs, key=lambda r: r["latency_ms"])
    by_cost = sorted(runs, key=lambda r: r["cost_proxy"])
    by_tokens = sorted(runs, key=lambda r: r["tokens_approx"], reverse=True)

    summary = (
        f"Скорость: быстрее всех «{TIER_LABEL[by_latency[0]['tier']]}» "
        f"({by_latency[0]['latency_ms']} ms). "
        f"Ресурсы (cost≈): дешевле «{TIER_LABEL[by_cost[0]['tier']]}» "
        f"({by_cost[0]['cost_proxy']}). "
        f"Объём ответа (tokens≈): больше у «{TIER_LABEL[by_tokens[0]['tier']]}». "
        "Качество сравни глазами по текстам ниже и по вкладке Студия (судья Q)."
    )

    links = []
    for r in runs:
        mid = r.get("model_id") or r["requested_model"]
        if mid and mid != "auto" and "/" in str(mid):
            links.append(f"- [{mid}](https://openrouter.ai/{mid})")
        else:
            links.append(f"- `{mid}`")

    payload = {
        "challenge": "05-model-tiers",
        "base_url": base,
        "prompt": prompt,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "catalog_ids": ids,
        "picks": picks,
        "runs": runs,
        "summary": summary,
        "model_links": links,
        "ui": "https://aichallenge.arcilite.ru/ — Модели → Студия",
    }
    write_json(str(HERE / "results.json"), payload)

    md = [
        "# Challenge 05 — Версии моделей",
        "",
        f"Prod: `{base}` · {payload['exported_at']}",
        "",
        "## Запрос",
        "",
        prompt,
        "",
        "## Пики (начало / середина / конец каталога)",
        "",
        f"- Слабая: `{picks['weak']}`",
        f"- Средняя: `{picks['mid']}`",
        f"- Сильная: `{picks['strong']}`",
        "",
        "## Замеры",
        "",
        "| Tier | requested | resolved | latency | tokens≈ | cost≈ |",
        "|------|-----------|----------|---------|---------|-------|",
    ]
    for r in runs:
        md.append(
            f"| {TIER_LABEL[r['tier']]} | `{r['requested_model']}` | `{r['model_id']}` | "
            f"{r['latency_ms']} ms | {r['tokens_approx']} | {r['cost_proxy']} |"
        )
    md.extend(["", "## Ответы", ""])
    for r in runs:
        md.append(f"### {TIER_LABEL[r['tier']]} (`{r['model_id']}`)")
        md.append("")
        md.append(r["content"].strip() or "_(пусто)_")
        md.append("")
    md.extend(["## Вывод", "", summary, "", "## Ссылки на модели", ""])
    md.extend(links)
    md.extend(["", f"UI: {payload['ui']}", ""])
    (HERE / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {HERE / 'results.json'} and {HERE / 'RESULTS.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

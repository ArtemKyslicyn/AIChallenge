"""Turn a window of run traces into a ranked table.

The score is a proxy, not a truth: it says "this model answered more often,
faster, for less" and nothing about answer quality. It is published next to the
table so nobody mistakes it for one.
"""

from __future__ import annotations

from collections.abc import Iterable
from statistics import median

from app.domain.tracing import STATUS_OK, ModelAggregate, RunTrace

#: Shown in the Lab UI beside the ranking, so the number is never a black box.
PARETO_FORMULA = "score = успех ÷ время_ответа ÷ cost"

#: Below this, a latency number stops being a differentiator and starts being
#: noise that would dominate the whole ranking.
MIN_LATENCY_SECONDS = 0.2
MIN_COST_PROXY = 0.01

#: What an unmeasured run is worth. Neutral on purpose: a model with no data
#: must not outrank a measured one just for being unmeasured.
NEUTRAL_TOTAL_MS = 1000.0
NEUTRAL_COST_PROXY = 1.0


def pareto_score(
    success_rate: float, p50_total_ms: float | None, avg_cost_proxy: float | None
) -> float:
    latency_s = max((p50_total_ms or NEUTRAL_TOTAL_MS) / 1000.0, MIN_LATENCY_SECONDS)
    cost = max(avg_cost_proxy or NEUTRAL_COST_PROXY, MIN_COST_PROXY)
    return success_rate / latency_s / cost


def _p50(values: list[int]) -> float | None:
    return float(median(values)) if values else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate_models(traces: Iterable[RunTrace]) -> list[ModelAggregate]:
    """Group traces by the model that actually answered, best score first.

    Runs with no resolved model (an exhausted chain) are counted against
    nobody: attributing them to a model would blame it for being unreachable.
    """
    grouped: dict[str, list[RunTrace]] = {}
    for trace in traces:
        if trace.resolved_model_id:
            grouped.setdefault(trace.resolved_model_id, []).append(trace)

    aggregates: list[ModelAggregate] = []
    for model_id, rows in grouped.items():
        n = len(rows)
        success_rate = sum(1 for r in rows if r.status == STATUS_OK) / n
        p50_ttft = _p50([r.ttft_ms for r in rows if r.ttft_ms is not None])
        p50_total = _p50([r.total_ms for r in rows if r.total_ms is not None])
        avg_cost = _mean([r.cost_proxy for r in rows if r.cost_proxy is not None])
        aggregates.append(
            ModelAggregate(
                model_id=model_id,
                n=n,
                success_rate=success_rate,
                p50_ttft_ms=p50_ttft,
                p50_total_ms=p50_total,
                avg_cost_proxy=avg_cost,
                score=pareto_score(success_rate, p50_total, avg_cost),
            )
        )
    # Ties broken by model id so the table does not reshuffle between reloads.
    aggregates.sort(key=lambda a: (-a.score, a.model_id))
    return aggregates

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

#: How many judged runs a model needs before its quality is allowed to move it
#: in the ranking. Mirrors ``Settings.judge_min_runs`` so that a caller which
#: does not pass the knob ranks the same way as one that does.
DEFAULT_MIN_JUDGED_RUNS = 5


def pareto_score(
    quality_or_success: float, p50_total_ms: float | None, avg_cost_proxy: float | None
) -> float:
    """Value per second per unit of cost.

    The numerator is whatever :func:`ranking_quantity` decided is the honest
    measure of "how good is this model" right now — its judged quality once
    enough answers have been judged, and its bare success rate until then.
    """
    latency_s = max((p50_total_ms or NEUTRAL_TOTAL_MS) / 1000.0, MIN_LATENCY_SECONDS)
    cost = max(avg_cost_proxy or NEUTRAL_COST_PROXY, MIN_COST_PROXY)
    return quality_or_success / latency_s / cost


def ranking_quantity(
    *,
    success_rate: float,
    avg_quality: float | None,
    judged_n: int,
    min_judged_runs: int,
) -> float:
    """What the score divides by latency and cost: quality, or else success.

    Two conditions, and both matter. A missing average means nobody judged this
    model, so there is nothing to rank it by; too small a sample means the
    average exists but is mostly noise, and letting it decide would reshuffle
    the table on the strength of two dice rolls. Until both are satisfied the
    number is exactly the one this table showed before the judge existed.
    """
    if avg_quality is not None and judged_n >= min_judged_runs:
        return avg_quality
    return success_rate


def _p50(values: list[int]) -> float | None:
    return float(median(values)) if values else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate_models(
    traces: Iterable[RunTrace], *, min_judged_runs: int = DEFAULT_MIN_JUDGED_RUNS
) -> list[ModelAggregate]:
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
        # Only the rows a judge actually looked at. An unjudged run is missing
        # data, not a zero, and averaging it in would punish a model for the
        # sampler's dice instead of for its answers.
        verdicts = [r.quality_score for r in rows if r.quality_score is not None]
        avg_quality = _mean(verdicts)
        aggregates.append(
            ModelAggregate(
                model_id=model_id,
                n=n,
                success_rate=success_rate,
                p50_ttft_ms=p50_ttft,
                p50_total_ms=p50_total,
                avg_cost_proxy=avg_cost,
                score=pareto_score(
                    ranking_quantity(
                        success_rate=success_rate,
                        avg_quality=avg_quality,
                        judged_n=len(verdicts),
                        min_judged_runs=min_judged_runs,
                    ),
                    p50_total,
                    avg_cost,
                ),
                avg_quality=avg_quality,
                judged_n=len(verdicts),
            )
        )
    # Ties broken by model id so the table does not reshuffle between reloads.
    aggregates.sort(key=lambda a: (-a.score, a.model_id))
    return aggregates

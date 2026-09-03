"""Ranking math: one score per model, and the window aggregation behind it."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.application.pareto import PARETO_FORMULA, aggregate_models, pareto_score
from app.domain.tracing import STATUS_ERROR, STATUS_EXHAUSTED, STATUS_OK, RunTrace

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def trace(
    model: str | None,
    *,
    status: str = STATUS_OK,
    ttft_ms: int | None = 100,
    total_ms: int | None = 1000,
    cost: float | None = 1.0,
    minute: int = 0,
) -> RunTrace:
    return RunTrace(
        id=UUID(int=minute + 1),
        session_id=UUID(int=1),
        message_id=UUID(int=2),
        visitor_hash=None,
        preferred_model="auto",
        resolved_model_id=model,
        attempts=[],
        ttft_ms=ttft_ms,
        total_ms=total_ms,
        token_count_est=10,
        cost_proxy=cost,
        tool_rounds=0,
        tool_ok=None,
        status=status,
        created_at=NOW + timedelta(minutes=minute),
    )


def test_formula_is_published_next_to_the_math() -> None:
    assert "score" in PARETO_FORMULA


def test_score_rewards_success_and_punishes_latency_and_cost() -> None:
    assert pareto_score(1.0, 1000.0, 1.0) == 1.0
    assert pareto_score(0.5, 1000.0, 1.0) == 0.5
    assert pareto_score(1.0, 2000.0, 1.0) == 0.5
    assert pareto_score(1.0, 1000.0, 2.0) == 0.5


def test_score_falls_back_to_neutral_values_when_a_metric_is_missing() -> None:
    # A model with no measured latency must not outrank a measured one for free.
    assert pareto_score(1.0, None, None) == pareto_score(1.0, 1000.0, 1.0)


def test_score_clamps_absurdly_small_latency_and_cost() -> None:
    # 1 ms would otherwise divide by 0.001 and dominate every ranking.
    assert pareto_score(1.0, 1.0, 1.0) == 5.0
    assert pareto_score(1.0, 1000.0, 0.001) == 100.0


def test_zero_success_rate_scores_zero() -> None:
    assert pareto_score(0.0, 1000.0, 1.0) == 0.0


def test_aggregate_groups_by_resolved_model() -> None:
    rows = [
        trace("m1", total_ms=1000, ttft_ms=100, minute=0),
        trace("m1", total_ms=3000, ttft_ms=300, minute=1),
        trace("m2", total_ms=1000, ttft_ms=100, minute=2),
    ]
    by_model = {a.model_id: a for a in aggregate_models(rows)}
    assert by_model["m1"].n == 2
    assert by_model["m1"].p50_total_ms == 2000.0
    assert by_model["m1"].p50_ttft_ms == 200.0
    assert by_model["m2"].n == 1


def test_success_rate_counts_only_the_ok_status() -> None:
    rows = [
        trace("m1", status=STATUS_OK),
        trace("m1", status=STATUS_ERROR, minute=1),
        trace("m1", status=STATUS_OK, minute=2),
        trace("m1", status=STATUS_OK, minute=3),
    ]
    (agg,) = aggregate_models(rows)
    assert agg.n == 4
    assert agg.success_rate == 0.75


def test_runs_without_a_resolved_model_are_not_attributed_to_anyone() -> None:
    # An exhausted chain answered with no model; charging it to one would lie.
    assert aggregate_models([trace(None, status=STATUS_EXHAUSTED)]) == []


def test_missing_measurements_stay_null_rather_than_becoming_zero() -> None:
    rows = [trace("m1", ttft_ms=None, total_ms=None, cost=None)]
    (agg,) = aggregate_models(rows)
    assert agg.p50_ttft_ms is None
    assert agg.p50_total_ms is None
    assert agg.avg_cost_proxy is None
    assert agg.n == 1


def test_percentiles_ignore_the_rows_that_have_no_number() -> None:
    rows = [
        trace("m1", total_ms=None, ttft_ms=None, minute=0),
        trace("m1", total_ms=1000, ttft_ms=100, minute=1),
    ]
    (agg,) = aggregate_models(rows)
    assert agg.p50_total_ms == 1000.0
    assert agg.n == 2


def test_average_cost_ignores_unconfigured_models() -> None:
    rows = [trace("m1", cost=None), trace("m1", cost=2.0, minute=1)]
    (agg,) = aggregate_models(rows)
    assert agg.avg_cost_proxy == 2.0


def test_result_is_ordered_best_first() -> None:
    rows = [
        trace("slow", total_ms=4000, minute=0),
        trace("fast", total_ms=500, minute=1),
        trace("mid", total_ms=1000, minute=2),
    ]
    assert [a.model_id for a in aggregate_models(rows)] == ["fast", "mid", "slow"]


def test_empty_window_is_an_empty_table() -> None:
    assert aggregate_models([]) == []

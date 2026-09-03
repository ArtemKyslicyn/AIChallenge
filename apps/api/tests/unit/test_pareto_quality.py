"""The quality branch of the ranking: when it counts, and when it must not.

The load-bearing assertion in this file is the negative one. Turning the judge
on is allowed to add a column; it is not allowed to reorder yesterday's table
retroactively, so a model with a handful of judged runs keeps exactly the score
it had before anybody judged anything.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.application.pareto import (
    DEFAULT_MIN_JUDGED_RUNS,
    aggregate_models,
    pareto_score,
    ranking_quantity,
)
from app.domain.tracing import STATUS_OK, RunTrace

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def trace(
    model: str = "m1",
    *,
    quality: float | None = None,
    quality_model_id: str | None = None,
    minute: int = 0,
) -> RunTrace:
    return RunTrace(
        id=UUID(int=minute + 1),
        session_id=UUID(int=1),
        message_id=UUID(int=minute + 100),
        visitor_hash=None,
        preferred_model="auto",
        resolved_model_id=model,
        attempts=[],
        ttft_ms=100,
        total_ms=1000,
        token_count_est=10,
        cost_proxy=1.0,
        tool_rounds=0,
        tool_ok=None,
        status=STATUS_OK,
        created_at=NOW + timedelta(minutes=minute),
        quality_score=quality,
        quality_model_id=quality_model_id,
    )


def judged(n: int, score: float) -> list[RunTrace]:
    return [trace(quality=score, quality_model_id="judge-1", minute=i) for i in range(n)]


def test_quantity_is_success_until_the_sample_is_big_enough() -> None:
    assert ranking_quantity(success_rate=1.0, avg_quality=0.4, judged_n=2, min_judged_runs=5) == 1.0


def test_quantity_becomes_quality_once_the_sample_is_big_enough() -> None:
    assert ranking_quantity(success_rate=1.0, avg_quality=0.4, judged_n=5, min_judged_runs=5) == 0.4


def test_quantity_stays_success_when_nothing_was_judged() -> None:
    # `judged_n >= 0` is true for every model on earth; the missing average is
    # what actually decides here, and it must not read as a zero.
    assert (
        ranking_quantity(success_rate=0.9, avg_quality=None, judged_n=0, min_judged_runs=0) == 0.9
    )


def test_score_ignores_quality_until_there_are_enough_judged_runs() -> None:
    # Switching the judge on must not reorder the table behind the reader's back.
    rows = judged(2, 0.2)
    (agg,) = aggregate_models(rows, min_judged_runs=5)
    assert agg.judged_n == 2
    assert agg.avg_quality == pytest.approx(0.2)
    assert agg.score == pytest.approx(pareto_score(1.0, 1000.0, 1.0))


def test_score_uses_quality_once_the_sample_is_big_enough() -> None:
    rows = judged(7, 0.5)
    (agg,) = aggregate_models(rows, min_judged_runs=5)
    assert agg.judged_n == 7
    assert agg.avg_quality == pytest.approx(0.5)
    assert agg.score == pytest.approx(pareto_score(0.5, 1000.0, 1.0))


def test_average_quality_is_taken_over_the_judged_rows_only() -> None:
    # Counting an unjudged run as a zero would punish a model for the sampler's
    # dice rather than for its answers.
    rows = [*judged(2, 1.0), trace(minute=5), trace(minute=6)]
    (agg,) = aggregate_models(rows, min_judged_runs=5)
    assert agg.n == 4
    assert agg.judged_n == 2
    assert agg.avg_quality == pytest.approx(1.0)


def test_a_zero_verdict_is_a_judged_run() -> None:
    # 0.0 is a verdict ("the judge found this bad"), unlike None. It has to
    # count towards the sample, or a badly-rated model would never reach the
    # threshold that would demote it.
    rows = judged(5, 0.0)
    (agg,) = aggregate_models(rows, min_judged_runs=5)
    assert agg.judged_n == 5
    assert agg.avg_quality == 0.0
    assert agg.score == 0.0


def test_an_unjudged_window_looks_exactly_like_it_did_before_the_judge() -> None:
    rows = [trace(minute=i) for i in range(3)]
    (agg,) = aggregate_models(rows, min_judged_runs=5)
    assert agg.avg_quality is None
    assert agg.judged_n == 0
    assert agg.score == pytest.approx(pareto_score(1.0, 1000.0, 1.0))


def test_the_default_threshold_matches_the_configured_one() -> None:
    # aggregate_models is called without the knob in a few places; its default
    # has to be the same number the settings default to, or the ranking would
    # depend on which caller asked.
    assert DEFAULT_MIN_JUDGED_RUNS == 5
    rows = judged(4, 0.1)
    (agg,) = aggregate_models(rows)
    assert agg.score == pytest.approx(pareto_score(1.0, 1000.0, 1.0))

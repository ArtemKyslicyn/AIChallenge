"""The quality domain: one verdict about one answer, and what a trace keeps."""

from datetime import UTC, datetime
from uuid import UUID

from app.domain.quality import CRITERION_MAX, RUBRIC_CRITERIA, QualityVerdict
from app.domain.tracing import STATUS_OK, ModelAggregate, RunTrace


def test_verdict_keeps_the_sub_scores_it_was_built_from() -> None:
    verdict = QualityVerdict(
        score=0.8,
        sub_scores={"relevance": 4, "completeness": 4, "clarity": 4},
        judge_model_id="judge-1",
    )
    assert verdict.score == 0.8
    assert verdict.sub_scores["relevance"] == 4
    assert verdict.judge_model_id == "judge-1"


def test_the_rubric_is_a_fixed_ordered_tuple() -> None:
    # Порядок фиксирован: по нему собирается промпт и по нему же идёт разбор.
    assert RUBRIC_CRITERIA == ("relevance", "completeness", "clarity")
    assert CRITERION_MAX == 5


def test_a_trace_that_nobody_judged_carries_no_quality() -> None:
    # Не «ноль», а «неизвестно» — иначе несудённый прогон выглядел бы плохим.
    trace = RunTrace(
        id=UUID(int=1),
        session_id=UUID(int=2),
        message_id=UUID(int=3),
        visitor_hash=None,
        preferred_model="auto",
        resolved_model_id="m1",
        attempts=[],
        ttft_ms=100,
        total_ms=1000,
        token_count_est=10,
        cost_proxy=1.0,
        tool_rounds=0,
        tool_ok=None,
        status=STATUS_OK,
        created_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    assert trace.quality_score is None
    assert trace.quality_model_id is None


def test_an_aggregate_without_judged_runs_says_so_out_loud() -> None:
    # Среднее без размера выборки читается как факт, поэтому едут оба поля.
    aggregate = ModelAggregate(
        model_id="m1",
        n=3,
        success_rate=1.0,
        p50_ttft_ms=None,
        p50_total_ms=None,
        avg_cost_proxy=None,
        score=1.0,
    )
    assert aggregate.avg_quality is None
    assert aggregate.judged_n == 0

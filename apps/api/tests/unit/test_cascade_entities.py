"""The cascade vocabulary: three stages, and a verdict that says why."""

from app.domain.cascade import CASCADE_CHEAP, CASCADE_ESCALATED, CASCADE_OFF, ScoreVerdict


def test_verdict_carries_reason_when_rejected() -> None:
    verdict = ScoreVerdict(score=0.4, accepted=False, reason="refusal")
    assert verdict.accepted is False
    assert verdict.reason == "refusal"


def test_stages_are_distinct() -> None:
    assert len({CASCADE_OFF, CASCADE_CHEAP, CASCADE_ESCALATED}) == 3


def test_a_trace_defaults_to_the_cascade_being_off() -> None:
    # An untouched turn must never look like the cheap model answered it.
    from datetime import UTC, datetime
    from uuid import UUID

    from app.domain.tracing import STATUS_OK, RunTrace

    trace = RunTrace(
        id=UUID(int=1),
        session_id=UUID(int=2),
        message_id=UUID(int=3),
        visitor_hash=None,
        preferred_model="auto",
        resolved_model_id="m1",
        attempts=[],
        ttft_ms=None,
        total_ms=None,
        token_count_est=None,
        cost_proxy=None,
        tool_rounds=0,
        tool_ok=None,
        status=STATUS_OK,
        created_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    assert trace.cascade_stage == CASCADE_OFF
    assert trace.cheap_model_id is None
    assert trace.cheap_score is None

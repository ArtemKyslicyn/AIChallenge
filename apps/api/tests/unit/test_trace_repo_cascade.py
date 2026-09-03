"""The three cascade fields survive the row, and the window summary counts them."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.adapters.persistence.trace_repo import to_row, to_trace
from app.domain.cascade import (
    CASCADE_CHEAP,
    CASCADE_ESCALATED,
    CASCADE_OFF,
    CascadeSummary,
    cascade_summary_from_counts,
)
from app.domain.tracing import STATUS_OK, RunTrace

CREATED = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def sample(
    *, stage: str = CASCADE_ESCALATED, cheap: str | None = "cheap-1", score: float | None = 0.5
) -> RunTrace:
    return RunTrace(
        id=UUID(int=1),
        session_id=UUID(int=2),
        message_id=UUID(int=3),
        visitor_hash="v-hash",
        preferred_model="auto",
        resolved_model_id="strong-1",
        attempts=[],
        ttft_ms=120,
        total_ms=900,
        token_count_est=25,
        cost_proxy=1.5,
        tool_rounds=0,
        tool_ok=None,
        status=STATUS_OK,
        created_at=CREATED,
        cascade_stage=stage,
        cheap_model_id=cheap,
        cheap_score=score,
    )


def test_an_escalated_trace_survives_a_round_trip() -> None:
    assert to_trace(to_row(sample())) == sample()


def test_the_row_carries_the_stage_verbatim() -> None:
    row = to_row(sample(stage=CASCADE_CHEAP, score=1.0))
    assert row.cascade_stage == CASCADE_CHEAP
    assert row.cheap_model_id == "cheap-1"
    assert row.cheap_score == 1.0


def test_a_turn_without_the_cascade_round_trips_as_off() -> None:
    trace = sample(stage=CASCADE_OFF, cheap=None, score=None)
    restored = to_trace(to_row(trace))
    assert restored.cascade_stage == CASCADE_OFF
    assert restored.cheap_model_id is None
    assert restored.cheap_score is None


def test_the_summary_reports_the_escalation_share() -> None:
    summary = cascade_summary_from_counts(cheap=2, escalated=1)
    assert summary == CascadeSummary(total=3, cheap=2, escalated=1)
    assert summary is not None
    assert summary.escalation_rate == pytest.approx(1 / 3)


def test_a_window_the_cascade_never_touched_has_no_summary() -> None:
    # None, not zeroes: "the cascade did not run" and "it ran and escalated
    # nothing" are different facts, and the panel draws only the second.
    assert cascade_summary_from_counts(cheap=0, escalated=0) is None


def test_a_summary_without_escalations_is_still_a_summary() -> None:
    summary = cascade_summary_from_counts(cheap=4, escalated=0)
    assert summary is not None
    assert summary.escalation_rate == 0.0

"""The vote, the aggregate, and the export line — pure domain, no I/O."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.domain.feedback import (
    FEEDBACK_VALUES,
    MessageFeedback,
    ModelFeedbackStats,
    PreferenceRow,
    parse_feedback_value,
)
from app.domain.tracing import AttemptRecord

CREATED = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def test_only_two_values_exist() -> None:
    assert FEEDBACK_VALUES == {"up", "down"}


@pytest.mark.parametrize("raw", ["up", "down"])
def test_a_known_value_parses_to_itself(raw: str) -> None:
    assert parse_feedback_value(raw) == raw


@pytest.mark.parametrize("raw", ["", "UP", "meh", "1", "star"])
def test_anything_else_is_rejected_rather_than_coerced(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_feedback_value(raw)


def test_feedback_carries_the_session_without_a_second_lookup() -> None:
    vote = MessageFeedback(
        id=UUID(int=1),
        message_id=UUID(int=2),
        session_id=UUID(int=3),
        visitor_hash="v-hash",
        value="up",
        created_at=CREATED,
    )
    assert vote.session_id == UUID(int=3)


def test_no_votes_means_no_down_rate() -> None:
    stats = ModelFeedbackStats(model_id="m", ups=0, downs=0)
    assert stats.total == 0
    assert stats.down_rate == 0.0


@pytest.mark.parametrize(
    ("ups", "downs", "expected"),
    [(4, 0, 0.0), (0, 4, 1.0), (7, 3, 0.3), (1, 1, 0.5)],
)
def test_down_rate_is_downs_over_all_votes(ups: int, downs: int, expected: float) -> None:
    stats = ModelFeedbackStats(model_id="m", ups=ups, downs=downs)
    assert stats.total == ups + downs
    assert stats.down_rate == pytest.approx(expected)


def test_aggregates_are_frozen_so_a_reader_cannot_rewrite_them() -> None:
    stats = ModelFeedbackStats(model_id="m", ups=1, downs=1)
    with pytest.raises(AttributeError):
        stats.ups = 5  # type: ignore[misc]


def test_export_row_defaults_to_no_content_and_no_attempts() -> None:
    row = PreferenceRow(
        message_id=UUID(int=2), model_id="m", feedback="down", created_at=CREATED
    )
    assert row.attempts == []
    assert row.prompt is None
    assert row.answer is None
    assert row.ttft_ms is None


def test_export_row_keeps_the_attempt_journal_it_was_given() -> None:
    row = PreferenceRow(
        message_id=UUID(int=2),
        model_id="m2",
        feedback="up",
        created_at=CREATED,
        ttft_ms=120,
        total_ms=900,
        attempts=[AttemptRecord(model_id="m1", ok=False, reason="http_429")],
    )
    assert [a.model_id for a in row.attempts] == ["m1"]

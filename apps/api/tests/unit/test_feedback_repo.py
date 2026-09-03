"""Row ↔ entity mapping for votes, without needing a database."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.adapters.persistence.feedback_repo import EXPORT_ROW_LIMIT, to_feedback, to_row
from app.domain.feedback import MessageFeedback

CREATED = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def sample(value: str = "up") -> MessageFeedback:
    return MessageFeedback(
        id=UUID(int=1),
        message_id=UUID(int=2),
        session_id=UUID(int=3),
        visitor_hash="v-hash",
        value="up" if value == "up" else "down",
        created_at=CREATED,
    )


def test_vote_survives_a_round_trip_through_the_row() -> None:
    assert to_feedback(to_row(sample())) == sample()
    assert to_feedback(to_row(sample("down"))) == sample("down")


def test_the_row_stores_the_value_as_the_plain_string_the_check_allows() -> None:
    assert to_row(sample("down")).value == "down"


def test_an_unknown_stored_value_is_refused_rather_than_guessed() -> None:
    row = to_row(sample())
    row.value = "sideways"
    with pytest.raises(ValueError):
        to_feedback(row)


def test_the_export_reads_a_bounded_number_of_rows() -> None:
    # An export is a download, not a table scan: past this, narrow the window.
    assert EXPORT_ROW_LIMIT == 10000

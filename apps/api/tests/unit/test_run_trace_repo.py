"""Row ↔ entity mapping for run traces, without needing a database."""

from datetime import UTC, datetime
from uuid import UUID

from app.adapters.persistence.trace_repo import (
    AGGREGATE_ROW_LIMIT,
    attempt_from_json,
    to_row,
    to_trace,
)
from app.domain.tracing import STATUS_ABORTED, AttemptRecord, RunTrace

CREATED = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def sample() -> RunTrace:
    return RunTrace(
        id=UUID(int=1),
        session_id=UUID(int=2),
        message_id=UUID(int=3),
        visitor_hash="v-hash",
        preferred_model="auto",
        resolved_model_id="m2",
        attempts=[
            AttemptRecord(model_id="m1", ok=False, reason="http_429", error_kind="rate_limit"),
            AttemptRecord(model_id="m2", ok=True, ttft_ms=120),
        ],
        ttft_ms=120,
        total_ms=900,
        token_count_est=25,
        cost_proxy=1.5,
        tool_rounds=1,
        tool_ok=True,
        status=STATUS_ABORTED,
        created_at=CREATED,
    )


def test_trace_survives_a_round_trip_through_the_row() -> None:
    assert to_trace(to_row(sample())) == sample()


def test_attempts_are_stored_as_plain_json_values() -> None:
    row = to_row(sample())
    assert row.attempts == [
        {"model_id": "m1", "ok": False, "reason": "http_429", "ttft_ms": None,
         "error_kind": "rate_limit"},
        {"model_id": "m2", "ok": True, "reason": "", "ttft_ms": 120, "error_kind": None},
    ]


def test_a_partial_attempt_row_still_reads_back() -> None:
    # Rows written by an older build must not break the debug view.
    assert attempt_from_json({"model_id": "m1", "ok": True}) == AttemptRecord(
        model_id="m1", ok=True
    )
    assert attempt_from_json({}) == AttemptRecord(model_id="", ok=False)


def test_aggregation_reads_a_bounded_number_of_rows() -> None:
    # Without a ceiling, a wide window would scan the whole table.
    assert AGGREGATE_ROW_LIMIT == 5000

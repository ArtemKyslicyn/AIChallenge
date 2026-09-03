"""The observability entities: one journal entry, one run, one aggregate row."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.domain.ports import RunTraceRepository
from app.domain.tracing import (
    RUN_TRACE_STATUSES,
    STATUS_ABORTED,
    STATUS_ERROR,
    STATUS_EXHAUSTED,
    STATUS_OK,
    AttemptRecord,
    ModelAggregate,
    RunTrace,
)


def test_attempt_record_fields() -> None:
    a = AttemptRecord(model_id="m1", ok=False, reason="timeout", ttft_ms=None)
    assert a.model_id == "m1"
    assert a.ok is False
    assert a.reason == "timeout"
    assert a.ttft_ms is None
    assert a.error_kind is None


def test_attempt_record_is_immutable() -> None:
    a = AttemptRecord(model_id="m1", ok=True)
    with pytest.raises(FrozenInstanceError):
        a.ok = False  # type: ignore[misc]


def test_run_trace_holds_the_attempt_journal() -> None:
    trace = RunTrace(
        id=UUID(int=1),
        session_id=UUID(int=2),
        message_id=UUID(int=3),
        visitor_hash=None,
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
        tool_rounds=0,
        tool_ok=None,
        status=STATUS_OK,
        created_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    assert [a.model_id for a in trace.attempts] == ["m1", "m2"]
    assert trace.status in RUN_TRACE_STATUSES


def test_every_terminal_status_is_declared() -> None:
    assert RUN_TRACE_STATUSES == frozenset(
        {STATUS_OK, STATUS_ERROR, STATUS_ABORTED, STATUS_EXHAUSTED}
    )


def test_model_aggregate_allows_missing_percentiles() -> None:
    agg = ModelAggregate(
        model_id="m1",
        n=3,
        success_rate=1.0,
        p50_ttft_ms=None,
        p50_total_ms=None,
        avg_cost_proxy=None,
        score=0.0,
    )
    assert agg.n == 3
    assert agg.p50_ttft_ms is None


def test_repository_port_declares_the_three_operations() -> None:
    assert hasattr(RunTraceRepository, "save")
    assert hasattr(RunTraceRepository, "list_for_session")
    assert hasattr(RunTraceRepository, "aggregate")

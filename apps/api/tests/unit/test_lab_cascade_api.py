"""The two cascade-shaped responses the web client is typed against."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fakes import InMemoryRunTraceRepository
from fastapi.testclient import TestClient

from app.core.deps import get_run_traces, require_session
from app.core.settings import Settings
from app.domain.cascade import CASCADE_CHEAP, CASCADE_ESCALATED, CASCADE_OFF
from app.domain.entities import Session, SessionStatus
from app.domain.tracing import STATUS_OK, RunTrace
from app.main import create_app

SESSION_ID = UUID(int=7)


def trace(
    *,
    stage: str = CASCADE_OFF,
    cheap_model: str | None = None,
    cheap_score: float | None = None,
    minutes_ago: int = 1,
) -> RunTrace:
    return RunTrace(
        id=UUID(int=300 + minutes_ago),
        session_id=SESSION_ID,
        message_id=UUID(int=400 + minutes_ago),
        visitor_hash="v-hash",
        preferred_model="auto",
        resolved_model_id="model-a",
        attempts=[],
        ttft_ms=120,
        total_ms=1000,
        token_count_est=25,
        cost_proxy=1.0,
        tool_rounds=0,
        tool_ok=None,
        status=STATUS_OK,
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        cascade_stage=stage,
        cheap_model_id=cheap_model,
        cheap_score=cheap_score,
    )


@pytest.fixture
def traces() -> InMemoryRunTraceRepository:
    return InMemoryRunTraceRepository()


@pytest.fixture
def api(traces: InMemoryRunTraceRepository) -> Iterator[TestClient]:
    app = create_app(Settings(_env_file=None, use_fake_llm=True))  # type: ignore[call-arg]
    app.dependency_overrides[get_run_traces] = lambda: traces
    app.dependency_overrides[require_session] = lambda: Session(
        id=SESSION_ID,
        access_token="t",
        scenario_id="default",
        status=SessionStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    with TestClient(app) as client:
        yield client


def test_pareto_reports_the_escalation_summary(
    api: TestClient, traces: InMemoryRunTraceRepository
) -> None:
    traces.saved = [
        trace(stage=CASCADE_CHEAP, minutes_ago=1),
        trace(stage=CASCADE_CHEAP, minutes_ago=2),
        trace(stage=CASCADE_ESCALATED, minutes_ago=3),
    ]

    body = api.get("/api/v1/lab/pareto?hours=24").json()

    assert body["cascade"] == {
        "total": 3,
        "cheap": 2,
        "escalated": 1,
        "escalation_rate": pytest.approx(1 / 3),
    }


def test_pareto_omits_the_summary_when_the_cascade_never_ran(
    api: TestClient, traces: InMemoryRunTraceRepository
) -> None:
    traces.saved = [trace(), trace(minutes_ago=2)]
    assert api.get("/api/v1/lab/pareto?hours=24").json()["cascade"] is None


def test_an_empty_window_has_no_summary(api: TestClient) -> None:
    assert api.get("/api/v1/lab/pareto?hours=24").json()["cascade"] is None


def test_the_summary_follows_the_window(
    api: TestClient, traces: InMemoryRunTraceRepository
) -> None:
    traces.saved = [trace(stage=CASCADE_ESCALATED, minutes_ago=60 * 5)]
    assert api.get("/api/v1/lab/pareto?hours=1").json()["cascade"] is None
    assert api.get("/api/v1/lab/pareto?hours=24").json()["cascade"]["escalated"] == 1


def test_session_traces_carry_the_stage_and_the_verdict(
    api: TestClient, traces: InMemoryRunTraceRepository
) -> None:
    traces.saved = [trace(stage=CASCADE_ESCALATED, cheap_model="cheap-1", cheap_score=0.5)]

    (row,) = api.get(f"/api/v1/sessions/{SESSION_ID}/traces").json()["traces"]

    assert row["cascade_stage"] == "escalated"
    assert row["cheap_model_id"] == "cheap-1"
    assert row["cheap_score"] == 0.5


def test_a_trace_without_the_cascade_reports_off_and_nulls(
    api: TestClient, traces: InMemoryRunTraceRepository
) -> None:
    traces.saved = [trace()]
    row: dict[str, Any] = api.get(f"/api/v1/sessions/{SESSION_ID}/traces").json()["traces"][0]
    assert row["cascade_stage"] == "off"
    assert row["cheap_model_id"] is None
    assert row["cheap_score"] is None

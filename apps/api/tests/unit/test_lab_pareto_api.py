"""The two read routes over run traces, with the repository swapped out.

The response shapes here are the contract the Lab UI is typed against, so the
assertions name every key rather than poking at one field.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fakes import InMemoryRunTraceRepository
from fastapi.testclient import TestClient

from app.core.deps import get_run_traces, require_session
from app.core.settings import Settings
from app.domain.entities import Session, SessionStatus
from app.domain.tracing import STATUS_OK, AttemptRecord, RunTrace
from app.main import create_app

SESSION_ID = UUID(int=7)
OTHER_SESSION_ID = UUID(int=8)


def trace(
    *,
    session_id: UUID = SESSION_ID,
    model: str | None = "model-a",
    total_ms: int | None = 1000,
    cost: float | None = 1.0,
    minutes_ago: int = 1,
) -> RunTrace:
    return RunTrace(
        id=UUID(int=100 + minutes_ago),
        session_id=session_id,
        message_id=UUID(int=200 + minutes_ago),
        visitor_hash="v-hash",
        preferred_model="auto",
        resolved_model_id=model,
        attempts=[
            AttemptRecord(model_id="model-x", ok=False, reason="http_429"),
            AttemptRecord(model_id=model or "", ok=True, ttft_ms=120),
        ],
        ttft_ms=120,
        total_ms=total_ms,
        token_count_est=25,
        cost_proxy=cost,
        tool_rounds=0,
        tool_ok=None,
        status=STATUS_OK,
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
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


def test_pareto_answers_with_the_formula_and_the_window(api: TestClient) -> None:
    body = api.get("/api/v1/lab/pareto").json()
    assert body["hours"] == 24
    assert body["formula"]
    assert body["models"] == []


def test_pareto_row_carries_every_column_the_table_renders(
    api: TestClient, traces: InMemoryRunTraceRepository
) -> None:
    traces.saved = [trace(minutes_ago=1), trace(minutes_ago=2, total_ms=3000)]

    (row,) = api.get("/api/v1/lab/pareto?hours=24").json()["models"]

    assert row == {
        "model_id": "model-a",
        "n": 2,
        "success_rate": 1.0,
        "p50_ttft_ms": 120.0,
        "p50_total_ms": 2000.0,
        "avg_cost_proxy": 1.0,
        "score": pytest.approx(0.5),
    }


def test_unmeasured_columns_are_null_not_zero(
    api: TestClient, traces: InMemoryRunTraceRepository
) -> None:
    traces.saved = [trace(total_ms=None, cost=None)]
    (row,) = api.get("/api/v1/lab/pareto").json()["models"]
    assert row["p50_total_ms"] is None
    assert row["avg_cost_proxy"] is None


def test_pareto_window_is_bounded(api: TestClient) -> None:
    assert api.get("/api/v1/lab/pareto?hours=0").status_code == 422
    assert api.get("/api/v1/lab/pareto?hours=721").status_code == 422
    assert api.get("/api/v1/lab/pareto?hours=720").status_code == 200


def test_pareto_ignores_runs_outside_the_window(
    api: TestClient, traces: InMemoryRunTraceRepository
) -> None:
    traces.saved = [trace(minutes_ago=60 * 5)]
    assert api.get("/api/v1/lab/pareto?hours=1").json()["models"] == []
    assert api.get("/api/v1/lab/pareto?hours=24").json()["models"]


def test_pareto_needs_no_session_token(api: TestClient) -> None:
    # Aggregates are per model id and carry nothing about any visitor.
    assert api.get("/api/v1/lab/pareto").status_code == 200


def test_session_traces_return_the_debug_shape(
    api: TestClient, traces: InMemoryRunTraceRepository
) -> None:
    traces.saved = [trace()]

    body: dict[str, Any] = api.get(f"/api/v1/sessions/{SESSION_ID}/traces").json()

    (row,) = body["traces"]
    assert set(row) == {
        "message_id",
        "resolved_model_id",
        "status",
        "ttft_ms",
        "total_ms",
        "attempts",
        "created_at",
        # Added by the cascade (phase D); their own assertions live in
        # test_lab_cascade_api.py.
        "cascade_stage",
        "cheap_model_id",
        "cheap_score",
    }
    assert row["resolved_model_id"] == "model-a"
    assert row["status"] == "ok"
    assert row["ttft_ms"] == 120
    assert row["attempts"][0] == {
        "model_id": "model-x",
        "ok": False,
        "reason": "http_429",
        "ttft_ms": None,
        "error_kind": None,
    }


def test_session_traces_never_leak_another_session(
    api: TestClient, traces: InMemoryRunTraceRepository
) -> None:
    traces.saved = [trace(session_id=OTHER_SESSION_ID)]
    assert api.get(f"/api/v1/sessions/{SESSION_ID}/traces").json() == {"traces": []}


def test_session_traces_require_the_session_token() -> None:
    # Without the override, the real dependency runs: an unknown session or a
    # wrong token is a 404, never a listing.
    app = create_app(Settings(_env_file=None, use_fake_llm=True))  # type: ignore[call-arg]
    with TestClient(app) as client:
        assert client.get("/api/v1/sessions/not-a-uuid/traces").status_code == 404

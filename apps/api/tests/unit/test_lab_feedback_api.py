"""The two Lab feedback routes.

The response shapes here are the contract the Lab UI is typed against, so the
assertions name every key rather than poking at one field.
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fakes import InMemoryFeedbackRepository
from fastapi.testclient import TestClient

from app.application.feedback import preference_row_json
from app.core.deps import get_feedback
from app.core.settings import Settings
from app.domain.feedback import ModelFeedbackStats, PreferenceRow
from app.domain.tracing import AttemptRecord
from app.main import create_app

VISITOR_ID = "11111111-1111-1111-1111-111111111111"
STATS_URL = "/api/v1/lab/feedback-stats"
EXPORT_URL = "/api/v1/lab/preference-export"


@pytest.fixture
def votes() -> InMemoryFeedbackRepository:
    return InMemoryFeedbackRepository()


def build(votes: InMemoryFeedbackRepository, **overrides: Any) -> TestClient:
    settings = Settings(_env_file=None, use_fake_llm=True, **overrides)  # type: ignore[call-arg]
    app = create_app(settings)
    app.dependency_overrides[get_feedback] = lambda: votes
    return TestClient(app)


@pytest.fixture
def api(votes: InMemoryFeedbackRepository) -> Iterator[TestClient]:
    with build(votes) as client:
        yield client


def row(model_id: str, *, ups: int, downs: int) -> ModelFeedbackStats:
    return ModelFeedbackStats(model_id=model_id, ups=ups, downs=downs)


def test_stats_answer_with_the_window_and_an_empty_table(api: TestClient) -> None:
    assert api.get(STATS_URL).json() == {"hours": 24, "models": []}


def test_a_stats_row_carries_every_column_the_table_renders(
    api: TestClient, votes: InMemoryFeedbackRepository
) -> None:
    votes.rows = [row("model-a", ups=4, downs=6)]

    body = api.get(f"{STATS_URL}?hours=168").json()

    assert body["hours"] == 168
    assert body["models"] == [
        {
            "model_id": "model-a",
            "ups": 4,
            "downs": 6,
            "down_rate": pytest.approx(0.6),
            "penalized": True,
        }
    ]


def test_a_model_under_the_vote_floor_is_not_penalized(
    api: TestClient, votes: InMemoryFeedbackRepository
) -> None:
    votes.rows = [row("model-a", ups=0, downs=4)]
    (model,) = api.get(STATS_URL).json()["models"]
    assert model["down_rate"] == 1.0
    assert model["penalized"] is False


def test_the_thresholds_that_move_the_router_also_move_the_chip(
    votes: InMemoryFeedbackRepository,
) -> None:
    votes.rows = [row("model-a", ups=7, downs=3)]
    with build(votes, feedback_min_votes=5, feedback_down_rate_threshold=0.2) as api:
        (model,) = api.get(STATS_URL).json()["models"]
    assert model["penalized"] is True


def test_the_worst_model_is_listed_first(
    api: TestClient, votes: InMemoryFeedbackRepository
) -> None:
    votes.rows = [row("good", ups=9, downs=1), row("bad", ups=1, downs=9)]
    assert [m["model_id"] for m in api.get(STATS_URL).json()["models"]] == ["bad", "good"]


def test_stats_ask_the_repository_for_the_requested_window(
    api: TestClient, votes: InMemoryFeedbackRepository
) -> None:
    before = datetime.now(UTC) - timedelta(hours=1)
    api.get(f"{STATS_URL}?hours=1")
    assert votes.last_since is not None
    assert abs((votes.last_since - before).total_seconds()) < 5


def test_the_stats_window_is_bounded(api: TestClient) -> None:
    assert api.get(f"{STATS_URL}?hours=0").status_code == 422
    assert api.get(f"{STATS_URL}?hours=721").status_code == 422
    assert api.get(f"{STATS_URL}?hours=720").status_code == 200


def test_stats_need_no_session_token(api: TestClient) -> None:
    # Aggregates are per model id and carry nothing about any visitor.
    assert api.get(STATS_URL).status_code == 200


def preference(*, minutes_ago: int = 1, content: bool = True) -> PreferenceRow:
    return PreferenceRow(
        message_id=UUID(int=5),
        model_id="model-a",
        feedback="up",
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        ttft_ms=120,
        total_ms=900,
        attempts=[AttemptRecord(model_id="model-x", ok=False, reason="http_429")],
        prompt="как дела?" if content else None,
        answer="хорошо" if content else None,
    )


def enabled(votes: InMemoryFeedbackRepository, **overrides: Any) -> TestClient:
    return build(votes, feedback_export_enabled=True, **overrides)


def visitor() -> dict[str, str]:
    return {"X-Visitor-Id": VISITOR_ID}


def test_the_export_is_absent_until_it_is_switched_on(api: TestClient) -> None:
    assert api.get(EXPORT_URL, headers=visitor()).status_code == 404


def test_an_unidentified_caller_gets_the_same_404(votes: InMemoryFeedbackRepository) -> None:
    # Which of the two locks is shut must not be discoverable.
    with enabled(votes) as on, build(votes) as off:
        switched_on_but_anonymous = on.get(EXPORT_URL)
        identified_but_switched_off = off.get(EXPORT_URL, headers=visitor())

    assert switched_on_but_anonymous.status_code == 404
    assert switched_on_but_anonymous.json() == identified_but_switched_off.json()


def test_the_export_returns_ndjson_lines(votes: InMemoryFeedbackRepository) -> None:
    votes.exportable = [preference(), preference(minutes_ago=2)]
    with enabled(votes) as api:
        response = api.get(EXPORT_URL, headers=visitor())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert "attachment" in response.headers["content-disposition"]
    lines = [line for line in response.text.split("\n") if line]
    assert len(lines) == 2
    assert json.loads(lines[0])["message_id"] == str(UUID(int=5))


def test_the_export_line_carries_the_trace_but_not_the_content(
    votes: InMemoryFeedbackRepository,
) -> None:
    votes.exportable = [preference()]
    with enabled(votes) as api:
        line = json.loads(api.get(EXPORT_URL, headers=visitor()).text.strip())

    assert set(line) == {
        "message_id",
        "model_id",
        "feedback",
        "ttft_ms",
        "total_ms",
        "attempts",
        "created_at",
    }
    assert line["attempts"] == [
        {
            "model_id": "model-x",
            "ok": False,
            "reason": "http_429",
            "ttft_ms": None,
            "error_kind": None,
        }
    ]


def test_content_appears_only_behind_its_own_flag(votes: InMemoryFeedbackRepository) -> None:
    votes.exportable = [preference()]
    with enabled(votes, feedback_export_include_content=True) as api:
        line = json.loads(api.get(EXPORT_URL, headers=visitor()).text.strip())

    assert line["prompt"] == "как дела?"
    assert line["answer"] == "хорошо"


def test_the_export_window_is_bounded(votes: InMemoryFeedbackRepository) -> None:
    with enabled(votes) as api:
        assert api.get(f"{EXPORT_URL}?hours=0", headers=visitor()).status_code == 422
        assert api.get(f"{EXPORT_URL}?hours=721", headers=visitor()).status_code == 422
        assert api.get(f"{EXPORT_URL}?hours=720", headers=visitor()).status_code == 200


def test_the_export_skips_votes_outside_the_window(votes: InMemoryFeedbackRepository) -> None:
    votes.exportable = [preference(minutes_ago=60 * 5)]
    with enabled(votes) as api:
        assert api.get(f"{EXPORT_URL}?hours=1", headers=visitor()).text == ""
        assert api.get(f"{EXPORT_URL}?hours=24", headers=visitor()).text


def test_an_empty_export_is_an_empty_body_not_an_error(
    votes: InMemoryFeedbackRepository,
) -> None:
    with enabled(votes) as api:
        response = api.get(EXPORT_URL, headers=visitor())
    assert response.status_code == 200
    assert response.text == ""


def test_a_row_with_no_content_omits_the_keys_entirely() -> None:
    # Absent, not null: a consumer of the default dump should not have to know
    # that a prompt field could have existed.
    payload = preference_row_json(preference(content=False))
    assert "prompt" not in payload
    assert "answer" not in payload


def test_a_row_with_content_spells_both_keys_out() -> None:
    payload = preference_row_json(preference())
    assert payload["prompt"] == "как дела?"
    assert payload["answer"] == "хорошо"
    assert payload["created_at"].startswith("20")

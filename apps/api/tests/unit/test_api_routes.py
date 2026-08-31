"""HTTP-level tests that need no database: probe, CORS, and the error shape."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app


def client(**overrides: Any) -> TestClient:
    settings = Settings(_env_file=None, use_fake_llm=True, **overrides)
    return TestClient(create_app(settings))


@pytest.fixture
def api() -> Iterator[TestClient]:
    with client() as c:
        yield c


def test_health(api: TestClient) -> None:
    assert api.get("/api/v1/health").json() == {"status": "ok"}


def test_probe_reports_the_model_that_answered(api: TestClient) -> None:
    response = api.post("/api/v1/llm/complete", json={"prompt": "ping"})
    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == "fake-model"
    assert body["content"]


def test_probe_streams_model_first_and_message_end_last(api: TestClient) -> None:
    response = api.post("/api/v1/llm/complete", json={"prompt": "ping", "stream": True})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert response.headers["x-accel-buffering"] == "no"

    events = [
        line[len("event: ") :] for line in response.text.splitlines() if line.startswith("event: ")
    ]
    assert events[0] == "model"
    assert events[-1] == "message_end"
    assert "fake-model" in response.text


def test_probe_disabled_returns_404_in_the_shared_error_shape() -> None:
    with client(llm_probe_enabled=False) as api:
        response = api.post("/api/v1/llm/complete", json={"prompt": "ping"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "probe_disabled",
            "message": "The LLM probe is disabled by configuration.",
        }
    }


def test_probe_without_prompt_or_messages_is_422(api: TestClient) -> None:
    response = api.post("/api/v1/llm/complete", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "message_validation"


def test_malformed_session_id_is_404_not_a_crash(api: TestClient) -> None:
    # Resolved before any database access, so this works without Postgres.
    response = api.get("/api/v1/sessions/not-a-uuid", headers={"X-Session-Token": "x"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_404"


def test_no_cors_headers_by_default(api: TestClient) -> None:
    response = api.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_the_configured_dev_origin() -> None:
    origin = "http://localhost:5173"
    with client(cors_allow_origins=origin) as api:
        response = api.options(
            "/api/v1/sessions",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-Session-Token",
            },
        )
    assert response.headers["access-control-allow-origin"] == origin
    assert "x-session-token" in response.headers["access-control-allow-headers"].lower()


def test_real_provider_without_a_model_chain_fails_at_startup() -> None:
    app = create_app(Settings(_env_file=None, llm_api_key="present", llm_model_chain=""))
    with pytest.raises(RuntimeError, match="LLM_MODEL_CHAIN"):
        with TestClient(app):
            pass

"""One real turn, one real vote, and the two reads that follow it."""

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.settings import Settings
from app.main import create_app

pytestmark = pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="set RUN_INTEGRATION=1")

VISITOR = {"X-Visitor-Id": "11111111-1111-1111-1111-111111111111"}


async def answer(api: AsyncClient) -> tuple[str, dict[str, str]]:
    """Send one message and return the assistant message id with its headers."""
    created = await api.post("/api/v1/sessions", json={})
    body = created.json()
    headers = {"X-Session-Token": body["access_token"]}
    async with api.stream(
        "POST",
        f"/api/v1/sessions/{body['id']}/messages",
        json={"content": "привет"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            pass
    messages = (await api.get(f"/api/v1/sessions/{body['id']}/messages", headers=headers)).json()
    assistant = [m for m in messages if m["role"] == "assistant"]
    return assistant[-1]["id"], headers


async def test_a_vote_survives_the_round_trip_into_the_lab_table(api: AsyncClient) -> None:
    message_id, headers = await answer(api)

    voted = await api.post(
        f"/api/v1/messages/{message_id}/feedback",
        json={"value": "down"},
        headers=headers | VISITOR,
    )
    assert voted.status_code == 200
    assert voted.json() == {"message_id": message_id, "value": "down"}

    stats = (await api.get("/api/v1/lab/feedback-stats?hours=1")).json()
    (model,) = stats["models"]
    assert model["model_id"] == "fake-model"
    assert model["downs"] == 1 and model["ups"] == 0
    assert model["penalized"] is False  # one vote is under the floor


async def test_a_second_vote_replaces_rather_than_adds(api: AsyncClient) -> None:
    message_id, headers = await answer(api)
    for value in ("down", "up"):
        await api.post(
            f"/api/v1/messages/{message_id}/feedback", json={"value": value}, headers=headers
        )

    (model,) = (await api.get("/api/v1/lab/feedback-stats?hours=1")).json()["models"]
    assert (model["ups"], model["downs"]) == (1, 0)


async def test_the_export_dumps_the_vote_with_its_trace(
    api: AsyncClient, migrated_database: str, engine: AsyncEngine
) -> None:
    message_id, headers = await answer(api)
    await api.post(
        f"/api/v1/messages/{message_id}/feedback", json={"value": "up"}, headers=headers
    )

    # A second app, because the export is off in the default configuration.
    app = create_app(
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            use_fake_llm=True,
            database_url=migrated_database,
            feedback_export_enabled=True,
        )
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ops:
            response = await ops.get("/api/v1/lab/preference-export?hours=1", headers=VISITOR)

    assert response.status_code == 200
    (line,) = [line for line in response.text.split("\n") if line]
    assert f'"{message_id}"' in line
    assert '"feedback": "up"' in line
    # Content stays out unless its own flag is on, even for an ops caller.
    assert "prompt" not in line

"""A real SSE turn with the cascade on must write the stage it took."""

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.llm.fake import FakeLLMProvider
from app.adapters.llm.router import ModelRouter
from app.core.settings import Settings
from app.main import create_app

pytestmark = pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="set RUN_INTEGRATION=1")

CHEAP_MODEL = "fake-model"

GOOD_ANSWER = (
    "Очередь работает по принципу FIFO, а стек — по принципу LIFO. "
    "Это определяет, какой элемент извлекается первым."
)


async def cascade_api(url: str, answer: str) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        use_fake_llm=True,
        database_url=url,
        max_message_chars=200,
        cascade_enabled=True,
        cascade_cheap_models=CHEAP_MODEL,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        # The provider is swapped after the container is built, so one fixture
        # can produce both an answer the scorer takes and one it refuses.
        app.state.container.router = ModelRouter(FakeLLMProvider(text=answer), [CHEAP_MODEL])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def turn(api: AsyncClient) -> str:
    created = await api.post("/api/v1/sessions", json={})
    assert created.status_code == 201
    body = created.json()
    headers = {"X-Session-Token": body["access_token"]}
    async with api.stream(
        "POST",
        f"/api/v1/sessions/{body['id']}/messages",
        json={"content": "Объясни, чем очередь отличается от стека."},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            pass
    return str(body["id"])


async def stage_row(engine: AsyncEngine, session_id: str) -> tuple[str, str | None, float | None]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT cascade_stage, cheap_model_id, cheap_score "
                    "FROM run_traces WHERE session_id = :sid"
                ),
                {"sid": session_id},
            )
        ).all()
    assert len(rows) == 1
    stage, cheap_model, score = rows[0]
    return stage, cheap_model, score


async def test_an_accepted_cheap_answer_is_stored_as_cheap(
    engine: AsyncEngine, migrated_database: str
) -> None:
    async for api in cascade_api(migrated_database, GOOD_ANSWER):
        session_id = await turn(api)
    stage, cheap_model, score = await stage_row(engine, session_id)
    assert stage == "cheap"
    assert cheap_model == CHEAP_MODEL
    assert score == 1.0


async def test_a_rejected_cheap_answer_is_stored_as_escalated(
    engine: AsyncEngine, migrated_database: str
) -> None:
    async for api in cascade_api(migrated_database, "нет"):
        session_id = await turn(api)
    stage, cheap_model, score = await stage_row(engine, session_id)
    assert stage == "escalated"
    assert cheap_model == CHEAP_MODEL
    assert score == 0.0

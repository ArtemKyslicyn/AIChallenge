"""A real SSE turn with the cascade on must write the stage it took."""

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

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


@dataclass(slots=True)
class Turn:
    session_id: str
    headers: dict[str, str]
    frames: list[str]

    def message_end(self) -> dict[str, Any]:
        payloads = [
            json.loads(line[len("data: ") :])
            for line in self.frames
            if line.startswith("data: ") and '"content"' in line
        ]
        assert len(payloads) == 1
        return payloads[0]


async def turn(api: AsyncClient) -> Turn:
    created = await api.post("/api/v1/sessions", json={})
    assert created.status_code == 201
    body = created.json()
    headers = {"X-Session-Token": body["access_token"]}
    frames: list[str] = []
    async with api.stream(
        "POST",
        f"/api/v1/sessions/{body['id']}/messages",
        json={"content": "Объясни, чем очередь отличается от стека."},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            frames.append(line)
    return Turn(session_id=str(body["id"]), headers=headers, frames=frames)


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
        answered = await turn(api)
    stage, cheap_model, score = await stage_row(engine, answered.session_id)
    assert stage == "cheap"
    assert cheap_model == CHEAP_MODEL
    assert score == 1.0


async def test_a_rejected_cheap_answer_is_stored_as_escalated(
    engine: AsyncEngine, migrated_database: str
) -> None:
    async for api in cascade_api(migrated_database, "нет"):
        answered = await turn(api)
    stage, cheap_model, score = await stage_row(engine, answered.session_id)
    assert stage == "escalated"
    assert cheap_model == CHEAP_MODEL
    assert score == 0.0
async def test_the_pareto_window_summarises_the_escalations(
    engine: AsyncEngine, migrated_database: str
) -> None:
    async for api in cascade_api(migrated_database, "нет"):
        await turn(api)
        body = (await api.get("/api/v1/lab/pareto?hours=24")).json()
    assert body["cascade"] == {
        "total": 1,
        "cheap": 0,
        "escalated": 1,
        "escalation_rate": 1.0,
    }


async def test_the_live_answer_carries_its_stage_in_message_end(
    engine: AsyncEngine, migrated_database: str
) -> None:
    """The badge must not wait for a reload — the last frame already knows."""
    async for api in cascade_api(migrated_database, "нет"):
        answered = await turn(api)
    assert answered.message_end()["cascade_stage"] == "escalated"


async def test_the_stage_survives_a_reload(engine: AsyncEngine, migrated_database: str) -> None:
    """History is what the reader comes back to; the badge has to be there too."""
    async for api in cascade_api(migrated_database, "нет"):
        answered = await turn(api)
        history = (
            await api.get(
                f"/api/v1/sessions/{answered.session_id}/messages", headers=answered.headers
            )
        ).json()
    stages = {m["role"]: m["cascade_stage"] for m in history}
    # The user's own turn was never a candidate for the cascade.
    assert stages == {"user": "off", "assistant": "escalated"}


async def test_an_untouched_turn_reads_back_as_off(
    engine: AsyncEngine, migrated_database: str
) -> None:
    async for api in cascade_api(migrated_database, GOOD_ANSWER):
        answered = await turn(api)
        history = (
            await api.get(
                f"/api/v1/sessions/{answered.session_id}/messages", headers=answered.headers
            )
        ).json()
    # "cheap" is not "escalated": the UI draws nothing, but the value is honest.
    assert [m["cascade_stage"] for m in history] == ["off", "cheap"]

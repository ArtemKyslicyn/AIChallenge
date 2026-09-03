"""A real SSE turn with the judge switched on — and one with it switched off.

The judge is stubbed rather than driven by FakeLLM: what needs proving here is
the wiring around it (an answer delivered, a detached task, a second database
session, the verdict landing on the right row), not that a fake provider can be
persuaded to emit a rubric-shaped JSON object.
"""

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.settings import Settings
from app.domain.quality import QualityVerdict
from app.main import create_app

pytestmark = pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="set RUN_INTEGRATION=1")

LONG_ENOUGH = "Расскажи подробно про устройство очереди сообщений и её гарантии. " * 3


class StubJudge:
    def __init__(self, verdict: QualityVerdict | None) -> None:
        self.verdict = verdict
        self.calls = 0

    async def judge(
        self, question: str, answer: str, *, answered_by: str
    ) -> QualityVerdict | None:
        self.calls += 1
        return self.verdict


async def start_session(api: AsyncClient) -> tuple[str, dict[str, str]]:
    response = await api.post("/api/v1/sessions", json={})
    assert response.status_code == 201
    body = response.json()
    return body["id"], {"X-Session-Token": body["access_token"]}


async def send(api: AsyncClient, session_id: str, headers: dict[str, str]) -> None:
    async with api.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": LONG_ENOUGH},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            pass


async def quality_rows(
    engine: AsyncEngine, session_id: str
) -> list[tuple[float | None, str | None]]:
    async with engine.connect() as conn:
        return [
            (score, model)
            for score, model in (
                await conn.execute(
                    text(
                        "SELECT quality_score, quality_model_id FROM run_traces "
                        "WHERE session_id = :sid"
                    ),
                    {"sid": session_id},
                )
            ).all()
        ]


def settings_for(url: str, **overrides: object) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        use_fake_llm=True,
        database_url=url,
        max_message_chars=2000,
        **overrides,  # type: ignore[arg-type]
    )


async def test_a_judged_turn_gets_its_verdict_written_after_the_answer(
    engine: AsyncEngine, migrated_database: str
) -> None:
    app = create_app(
        settings_for(
            migrated_database,
            judge_model="judge-1",
            judge_sample_rate=1.0,
            judge_min_answer_chars=1,
        )
    )
    async with app.router.lifespan_context(app):
        judge = StubJudge(QualityVerdict(score=0.6, judge_model_id="judge-1"))
        app.state.container.judge = judge
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as api:
            session_id, headers = await start_session(api)
            await send(api, session_id, headers)

            # The verdict is written by a task nobody awaited, so the row is
            # allowed to be a beat behind the response.
            for _ in range(50):
                rows = await quality_rows(engine, session_id)
                if rows and rows[0][0] is not None:
                    break
                await asyncio.sleep(0.02)

    assert judge.calls == 1
    assert rows == [(0.6, "judge-1")]


async def test_an_unconfigured_judge_leaves_the_turn_exactly_as_it_was(
    api: AsyncClient, engine: AsyncEngine
) -> None:
    # The default fixture has no JUDGE_MODEL: the answer must be written the
    # way it always was, with both quality columns untouched.
    session_id, headers = await start_session(api)
    await send(api, session_id, headers)
    await asyncio.sleep(0.1)

    assert await quality_rows(engine, session_id) == [(None, None)]

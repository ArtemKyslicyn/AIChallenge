"""One real SSE turn must leave exactly one measured row behind."""

import json
import os

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="set RUN_INTEGRATION=1")


async def start_session(api: AsyncClient) -> tuple[str, dict[str, str]]:
    response = await api.post("/api/v1/sessions", json={})
    assert response.status_code == 201
    body = response.json()
    return body["id"], {"X-Session-Token": body["access_token"]}


async def send(api: AsyncClient, session_id: str, headers: dict[str, str]) -> None:
    async with api.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": "hello"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            pass


async def test_one_chat_turn_writes_one_run_trace(api: AsyncClient, engine: AsyncEngine) -> None:
    session_id, headers = await start_session(api)
    await send(api, session_id, headers)

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT resolved_model_id, status, ttft_ms, total_ms, attempts, "
                    "token_count_est, tool_rounds "
                    "FROM run_traces WHERE session_id = :sid"
                ),
                {"sid": session_id},
            )
        ).all()

    assert len(rows) == 1
    resolved, status, ttft_ms, total_ms, attempts, tokens, tool_rounds = rows[0]
    assert resolved == "fake-model"
    assert status == "ok"
    assert ttft_ms is not None and total_ms is not None
    assert tokens and tokens > 0
    assert tool_rounds == 0

    journal = attempts if isinstance(attempts, list) else json.loads(attempts)
    assert [(a["model_id"], a["ok"]) for a in journal] == [("fake-model", True)]


async def test_traces_endpoint_returns_the_row_for_its_own_session(
    api: AsyncClient, engine: AsyncEngine
) -> None:
    session_id, headers = await start_session(api)
    await send(api, session_id, headers)

    response = await api.get(f"/api/v1/sessions/{session_id}/traces", headers=headers)
    assert response.status_code == 200
    traces = response.json()["traces"]
    assert len(traces) == 1
    assert traces[0]["resolved_model_id"] == "fake-model"
    assert traces[0]["status"] == "ok"
    assert traces[0]["attempts"][0]["model_id"] == "fake-model"

    # Someone else's session token must not open this window.
    other = await api.get(
        f"/api/v1/sessions/{session_id}/traces", headers={"X-Session-Token": "not-the-token"}
    )
    assert other.status_code == 404


async def test_pareto_window_ranks_the_model_that_answered(
    api: AsyncClient, engine: AsyncEngine
) -> None:
    session_id, headers = await start_session(api)
    await send(api, session_id, headers)

    body = (await api.get("/api/v1/lab/pareto?hours=24")).json()
    assert body["hours"] == 24
    assert body["formula"]
    models = {row["model_id"]: row for row in body["models"]}
    assert models["fake-model"]["n"] >= 1
    assert models["fake-model"]["success_rate"] == 1.0

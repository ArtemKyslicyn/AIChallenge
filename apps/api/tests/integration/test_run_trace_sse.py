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

"""What happens to an answer when the reader hangs up mid-stream.

This needs a real server. Closing an httpx ASGITransport response only closes
the async generator (GeneratorExit); uvicorn additionally *cancels* the request
task when the socket goes away, and cancellation is what breaks a naive write
in a finally block.
"""

import asyncio
import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="set RUN_INTEGRATION=1")


async def test_partial_answer_survives_a_client_hangup(live_url: str) -> None:
    async with httpx.AsyncClient(base_url=live_url, timeout=10) as client:
        created = await client.post("/api/v1/sessions", json={})
        assert created.status_code == 201
        session = created.json()
        headers = {"X-Session-Token": session["access_token"]}
        messages_url = f"/api/v1/sessions/{session['id']}/messages"

        seen_tokens = 0
        async with client.stream(
            "POST", messages_url, json={"content": "привет"}, headers=headers
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith('data: {"text"'):
                    seen_tokens += 1
                    if seen_tokens >= 2:
                        break  # drop the connection mid-answer

        assert seen_tokens >= 2

        # The write happens outside the cancelled request task, so give it a
        # moment to land before reading the row back.
        for _ in range(50):
            history = (await client.get(messages_url, headers=headers)).json()
            assistant = [m for m in history if m["role"] == "assistant"]
            if assistant and assistant[0]["content"]:
                break
            await asyncio.sleep(0.1)

        assert [m["content"] for m in history if m["role"] == "user"] == ["привет"]
        assert len(assistant) == 1
        assert assistant[0]["content"], "частичный ответ потерян при обрыве клиента"
        assert assistant[0]["model_id"], "модель не записана при обрыве клиента"
        assert assistant[0]["content"].endswith("[прервано]")

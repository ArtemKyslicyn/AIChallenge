import json
import os

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="set RUN_INTEGRATION=1")


async def start_session(api: AsyncClient) -> tuple[str, dict[str, str]]:
    response = await api.post("/api/v1/sessions", json={})
    assert response.status_code == 201
    body = response.json()
    return body["id"], {"X-Session-Token": body["access_token"]}


async def read_sse(api: AsyncClient, url: str, headers: dict[str, str], content: str):
    events: list[tuple[str, dict]] = []
    async with api.stream("POST", url, json={"content": content}, headers=headers) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        name = ""
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((name, json.loads(line[len("data: ") :])))
    return events


async def test_full_sse_round_trip_persists_model_id(api: AsyncClient) -> None:
    session_id, headers = await start_session(api)
    events = await read_sse(api, f"/api/v1/sessions/{session_id}/messages", headers, "hello")

    names = [name for name, _ in events]
    assert names[0] == "model"
    assert names[-1] == "message_end"
    assert set(names[1:-1]) == {"token"}

    model_id = events[0][1]["model_id"]
    end = events[-1][1]
    assert end["model_id"] == model_id
    assert end["content"] == "".join(d["text"] for n, d in events if n == "token")

    # The regression that matters: the final update_content runs after the
    # response body is done, so a request-scoped DB session would be closed.
    history = (await api.get(f"/api/v1/sessions/{session_id}/messages", headers=headers)).json()
    assistant = [m for m in history if m["role"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["content"] == end["content"]
    assert assistant[0]["model_id"] == model_id
    assert [m["content"] for m in history if m["role"] == "user"] == ["hello"]


async def test_stored_message_can_be_replayed(api: AsyncClient) -> None:
    session_id, headers = await start_session(api)
    events = await read_sse(api, f"/api/v1/sessions/{session_id}/messages", headers, "hi")
    end = events[-1][1]

    response = await api.get(
        f"/api/v1/sessions/{session_id}/stream",
        params={"message_id": end["message_id"]},
        headers=headers,
    )
    assert response.status_code == 200
    assert f'"model_id": "{end["model_id"]}"' in response.text
    assert "event: message_end" in response.text


async def test_replay_of_an_unknown_message_is_404(api: AsyncClient) -> None:
    session_id, headers = await start_session(api)
    response = await api.get(
        f"/api/v1/sessions/{session_id}/stream",
        params={"message_id": "00000000-0000-0000-0000-000000000000"},
        headers=headers,
    )
    assert response.status_code == 404


async def test_wrong_token_writes_nothing(api: AsyncClient) -> None:
    session_id, headers = await start_session(api)
    bad = {"X-Session-Token": "not-the-token"}

    messages_url = f"/api/v1/sessions/{session_id}/messages"
    assert (await api.post(messages_url, json={"content": "x"}, headers=bad)).status_code == 404
    assert (await api.get(messages_url, headers=bad)).status_code == 404

    history = (await api.get(f"/api/v1/sessions/{session_id}/messages", headers=headers)).json()
    assert history == []


async def test_missing_token_is_404(api: AsyncClient) -> None:
    session_id, _ = await start_session(api)
    assert (await api.get(f"/api/v1/sessions/{session_id}/messages")).status_code == 404


async def test_oversized_message_is_rejected_before_the_stream_opens(api: AsyncClient) -> None:
    session_id, headers = await start_session(api)
    response = await api.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": "x" * 201},  # max_message_chars is 200 in the fixture
        headers=headers,
    )
    assert response.status_code == 422
    assert "text/event-stream" not in response.headers.get("content-type", "")

    history = (await api.get(f"/api/v1/sessions/{session_id}/messages", headers=headers)).json()
    assert history == []


async def test_session_metadata_never_echoes_the_token(api: AsyncClient) -> None:
    session_id, headers = await start_session(api)
    body = (await api.get(f"/api/v1/sessions/{session_id}", headers=headers)).json()
    assert body["status"] == "active"
    assert "access_token" not in body

"""HTTP routes for session-scoped guest MCP."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.deps import require_session
from app.core.settings import Settings
from app.domain.entities import Session, SessionStatus
from app.main import create_app

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
SESSION_ID = UUID(int=42)
TOKEN = "guest-session-token"
BASE = f"/api/v1/sessions/{SESSION_ID}/guest-mcp"


class _FakeGuestClient:
    async def handshake(self, url: str, token: str) -> tuple[str, ...]:
        return ("echo",)

    async def call_tool(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("not used in route tests")


class _AuthFailGuestClient:
    async def handshake(self, url: str, token: str) -> tuple[str, ...]:
        from app.application.guest_mcp import GuestMcpAuthError

        raise GuestMcpAuthError("bad")

    async def call_tool(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("not used")


class _TimeoutGuestClient:
    async def handshake(self, url: str, token: str) -> tuple[str, ...]:
        raise TimeoutError("slow")

    async def call_tool(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("not used")


@pytest.fixture
def api() -> Iterator[TestClient]:
    app = create_app(Settings(_env_file=None, use_fake_llm=True))  # type: ignore[call-arg]
    app.dependency_overrides[require_session] = lambda: Session(
        id=SESSION_ID,
        access_token=TOKEN,
        scenario_id="default",
        status=SessionStatus.ACTIVE,
        created_at=NOW,
    )
    with TestClient(app) as client:
        client.app.state.container.guest_mcp_client = _FakeGuestClient()
        yield client


def auth() -> dict[str, str]:
    return {"X-Session-Token": TOKEN}


def assert_no_token_in_payload(payload: object) -> None:
    raw = json.dumps(payload)
    assert "token" not in raw.lower()


def test_connect_and_list_without_token(api: TestClient) -> None:
    connect = api.post(
        BASE,
        json={
            "name": "kit",
            "url": "https://kit.example.com/mcp",
            "token": "secret-bearer",
        },
        headers=auth(),
    )
    assert connect.status_code == 200
    body = connect.json()
    assert_no_token_in_payload(body)
    assert body["name"] == "kit"
    assert body["tool_names"] == ["echo"]
    assert body["status"] == "connected"

    listed = api.get(BASE, headers=auth())
    assert listed.status_code == 200
    list_body = listed.json()
    assert_no_token_in_payload(list_body)
    assert len(list_body["servers"]) == 1
    assert list_body["servers"][0]["id"] == body["id"]


def test_connect_blocked_url_returns_400(api: TestClient) -> None:
    response = api.post(
        BASE,
        json={
            "name": "bad",
            "url": "https://169.254.169.254/mcp",
            "token": "x",
        },
        headers=auth(),
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["message"]
    assert_no_token_in_payload(body)


def test_connect_unauthorized_returns_401(api: TestClient) -> None:
    api.app.state.container.guest_mcp_client = _AuthFailGuestClient()
    response = api.post(
        BASE,
        json={
            "name": "kit",
            "url": "https://kit.example.com/mcp",
            "token": "wrong",
        },
        headers=auth(),
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Неверный токен сервера."
    assert_no_token_in_payload(response.json())


def test_connect_timeout_returns_504(api: TestClient) -> None:
    api.app.state.container.guest_mcp_client = _TimeoutGuestClient()
    response = api.post(
        BASE,
        json={
            "name": "kit",
            "url": "https://kit.example.com/mcp",
            "token": "x",
        },
        headers=auth(),
    )
    assert response.status_code == 504
    assert response.json()["error"]["message"] == "Сервер не ответил за 8 секунд."
    assert_no_token_in_payload(response.json())

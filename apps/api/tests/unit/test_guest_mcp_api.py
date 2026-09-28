"""HTTP routes for session-scoped guest MCP."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.auth import require_auth_user
from app.core.deps import require_session
from app.core.settings import Settings
from app.domain.auth import UserAccount
from app.domain.entities import Session, SessionStatus
from app.main import create_app

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
SESSION_ID = UUID(int=42)
USER_ID = UUID(int=7)
OTHER_USER_ID = UUID(int=8)
TOKEN = "guest-session-token"
BASE = f"/api/v1/sessions/{SESSION_ID}/guest-mcp"


def _user(user_id: UUID = USER_ID) -> UserAccount:
    return UserAccount(
        id=user_id,
        email=f"u{user_id.int}@example.com",
        password_hash="x",
        display_name="U",
    )


@pytest.fixture(autouse=True)
def _stub_guest_mcp_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    import ipaddress

    from app.domain import guest_mcp as domain_guest_mcp

    def fake_resolve(host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        return (ipaddress.ip_address("8.8.8.8"),)

    monkeypatch.setattr(domain_guest_mcp, "_default_resolve", fake_resolve)


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
    app.dependency_overrides[require_auth_user] = lambda: _user()
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


def test_guest_mcp_without_login_returns_401() -> None:
    app = create_app(Settings(_env_file=None, use_fake_llm=True))  # type: ignore[call-arg]
    app.dependency_overrides[require_session] = lambda: Session(
        id=SESSION_ID,
        access_token=TOKEN,
        scenario_id="default",
        status=SessionStatus.ACTIVE,
        created_at=NOW,
    )
    with TestClient(app) as client:
        response = client.get(BASE, headers=auth())
    assert response.status_code == 401
    assert "вход" in response.json()["error"]["message"].lower()
    assert_no_token_in_payload(response.json())


def test_list_is_isolated_per_user(api: TestClient) -> None:
    connect = api.post(
        BASE,
        json={"name": "kit", "url": "https://kit.example.com/mcp", "token": "secret-bearer"},
        headers=auth(),
    )
    assert connect.status_code == 200
    api.app.dependency_overrides[require_auth_user] = lambda: _user(OTHER_USER_ID)
    listed = api.get(BASE, headers=auth())
    assert listed.status_code == 200
    assert listed.json()["servers"] == []


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

import pytest
from uuid import uuid4

from app.adapters.persistence.guest_mcp_memory import InMemoryGuestMcpRegistry
from app.application.guest_mcp import (
    GuestMcpAuthError,
    connect_guest_mcp,
    list_guest_mcp,
)
from app.domain.guest_mcp import GuestMcpRecord, GuestMcpServer, GuestMcpUrlError


class _FakeClient:
    async def handshake(self, url: str, token: str) -> tuple[str, ...]:
        assert token == "tok"
        return ("echo", "git_status")

    async def call_tool(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("not in connect")


class _NoopAnalytics:
    def __init__(self) -> None:
        self.names: list[str] = []
        self.props: list[dict[str, object]] = []

    async def capture(self, events: list[object]) -> None:
        for event in events:
            self.names.append(getattr(event, "name", ""))
            self.props.append(dict(getattr(event, "properties", {}) or {}))

    async def aclose(self) -> None:
        return None


async def test_registry_roundtrip() -> None:
    reg = InMemoryGuestMcpRegistry()
    sid = uuid4()
    rec = GuestMcpRecord(
        server=GuestMcpServer(
            id=uuid4(),
            name="kit",
            url="https://kit.example.com/mcp",
            enabled=True,
            tool_names=("echo",),
            status="connected",
        ),
        token="secret-token",
    )
    await reg.put(sid, rec)
    listed = await reg.list(sid)
    assert listed[0].token == "secret-token"
    assert listed[0].server.name == "kit"
    assert await reg.list(uuid4()) == ()


async def test_connect_lists_without_token() -> None:
    session_id = uuid4()
    analytics = _NoopAnalytics()
    registry = InMemoryGuestMcpRegistry()
    server = await connect_guest_mcp(
        session_id=session_id,
        name="kit",
        url="https://kit.example.com/mcp",
        token="tok",
        client=_FakeClient(),
        registry=registry,
        analytics=analytics,
        distinct_id="v1",
        allow_loopback=False,
    )
    listed = await list_guest_mcp(session_id, registry)
    assert server.tool_names == ("echo", "git_status")
    assert listed[0].id == server.id
    assert listed[0].tool_names == ("echo", "git_status")
    assert not hasattr(listed[0], "token")
    assert analytics.names == ["guest_mcp_connect_started", "guest_mcp_connect_ok"]
    ok_props = analytics.props[1]
    assert ok_props.get("url_host") == "kit.example.com"
    assert ok_props.get("tool_count") == 2
    assert all("token" not in p for p in analytics.props)


async def test_connect_ssrf_emits_fail() -> None:
    session_id = uuid4()
    analytics = _NoopAnalytics()
    registry = InMemoryGuestMcpRegistry()
    with pytest.raises(GuestMcpUrlError):
        await connect_guest_mcp(
            session_id=session_id,
            name="kit",
            url="https://169.254.169.254/mcp",
            token="tok",
            client=_FakeClient(),
            registry=registry,
            analytics=analytics,
            distinct_id="v1",
            allow_loopback=False,
        )
    assert analytics.names == ["guest_mcp_connect_started", "guest_mcp_connect_fail"]
    assert analytics.props[-1].get("reason") == "ssrf"


class _TimeoutClient:
    async def handshake(self, url: str, token: str) -> tuple[str, ...]:
        raise TimeoutError("slow")

    async def call_tool(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("not in connect")


async def test_connect_timeout_emits_fail() -> None:
    session_id = uuid4()
    analytics = _NoopAnalytics()
    registry = InMemoryGuestMcpRegistry()
    with pytest.raises(TimeoutError):
        await connect_guest_mcp(
            session_id=session_id,
            name="kit",
            url="https://kit.example.com/mcp",
            token="tok",
            client=_TimeoutClient(),
            registry=registry,
            analytics=analytics,
            distinct_id="v1",
            allow_loopback=False,
        )
    assert analytics.names == ["guest_mcp_connect_started", "guest_mcp_connect_fail"]
    assert analytics.props[-1].get("reason") == "timeout"


class _AuthFailClient:
    async def handshake(self, url: str, token: str) -> tuple[str, ...]:
        raise GuestMcpAuthError("bad token")

    async def call_tool(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("not in connect")


async def test_connect_unauthorized_emits_fail() -> None:
    session_id = uuid4()
    analytics = _NoopAnalytics()
    registry = InMemoryGuestMcpRegistry()
    with pytest.raises(GuestMcpAuthError):
        await connect_guest_mcp(
            session_id=session_id,
            name="kit",
            url="https://kit.example.com/mcp",
            token="tok",
            client=_AuthFailClient(),
            registry=registry,
            analytics=analytics,
            distinct_id="v1",
            allow_loopback=False,
        )
    assert analytics.names == ["guest_mcp_connect_started", "guest_mcp_connect_fail"]
    assert analytics.props[-1].get("reason") == "unauthorized"

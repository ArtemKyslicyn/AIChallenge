from uuid import uuid4

from app.adapters.persistence.guest_mcp_memory import InMemoryGuestMcpRegistry
from app.domain.guest_mcp import GuestMcpRecord, GuestMcpServer


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

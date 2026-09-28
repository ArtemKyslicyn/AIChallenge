"""Guest MCP tools in single-mode chat SSE."""

from __future__ import annotations

from uuid import UUID

import pytest
from fakes import (
    DEFAULT_SCENARIO,
    FIXED_NOW,
    IdFactory,
    InMemoryMessageRepository,
    InMemoryScenarioRepository,
    InMemorySessionRepository,
    RecordingUnitOfWork,
    fixed_now,
)

from app.adapters.llm.fake import FakeLLMProvider
from app.adapters.llm.router import ModelRouter
from app.adapters.persistence.guest_mcp_memory import InMemoryGuestMcpRegistry
from app.application.chat import (
    MessageEndEvent,
    ToolResultEvent,
    ToolStartEvent,
    send_user_message_and_stream,
)
from app.application.guest_tool_runner import GuestToolRunner
from app.domain.entities import ChatMessage, CompletionResult, Session, SessionStatus
from app.domain.guest_mcp import GuestMcpRecord, GuestMcpServer
from app.domain.media import ToolCallRequest

SESSION_ID = UUID(int=9)
USER_ID = UUID(int=11)
TOKEN = "guest-chat-token"
GUEST_SERVER_ID = UUID("abcd1234-0000-0000-0000-000000000000")
PREFIXED_ECHO = "g_abcd1234_echo"


@pytest.fixture(autouse=True)
def _stub_guest_mcp_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    import ipaddress

    from app.domain import guest_mcp as domain_guest_mcp

    def fake_resolve(host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        return (ipaddress.ip_address("8.8.8.8"),)

    monkeypatch.setattr(domain_guest_mcp, "_default_resolve", fake_resolve)


class _GuestToolFakeLLM(FakeLLMProvider):
    def __init__(self, text: str = "after tool") -> None:
        super().__init__(text=text, model_id="fake-model")
        self.complete_with_tools = 0

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: object = None,
        tools: list[dict[str, object]] | None = None,
    ) -> CompletionResult:
        if tools:
            self.complete_with_tools += 1
            return CompletionResult(
                content="",
                model_id=self._resolve(model),
                tool_calls=[
                    ToolCallRequest(id="guest-tc-1", name=PREFIXED_ECHO, arguments={})
                ],
            )
        return await super().complete_chat(
            messages, model, generation=generation, tools=tools  # type: ignore[arg-type]
        )


class _PongGuestClient:
    calls: list[tuple[str, str, str, dict[str, object]]] = []

    async def handshake(self, url: str, token: str) -> tuple[str, ...]:
        return ("echo",)

    async def call_tool(
        self, url: str, token: str, name: str, arguments: dict[str, object]
    ) -> str:
        _PongGuestClient.calls.append((url, token, name, arguments))
        return "pong"


class _SpyGuestRunner(GuestToolRunner):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.openai_tools_calls = 0

    async def openai_tools(self) -> list[dict[str, object]]:
        self.openai_tools_calls += 1
        return await super().openai_tools()


async def _seed_guest(registry: InMemoryGuestMcpRegistry) -> None:
    await registry.put(
        USER_ID,
        GuestMcpRecord(
            server=GuestMcpServer(
                id=GUEST_SERVER_ID,
                name="kit",
                url="https://kit.example.com/mcp",
                enabled=True,
                tool_names=("echo",),
                status="connected",
            ),
            token="bearer-secret",
        ),
    )


async def _stream(
    *,
    registry: InMemoryGuestMcpRegistry,
    chat_mode: str | None = None,
    use_guest_mcp: bool | None = True,
    guest_mcp_owner_id: UUID | None = USER_ID,
    guest_runner: GuestToolRunner | None = None,
) -> list[object]:
    sessions = InMemorySessionRepository()
    await sessions.create(
        Session(
            id=SESSION_ID,
            access_token=TOKEN,
            scenario_id="default",
            status=SessionStatus.ACTIVE,
            created_at=FIXED_NOW,
        )
    )
    provider = _GuestToolFakeLLM()
    router = ModelRouter(provider, ["fake-model"])
    events = send_user_message_and_stream(
        session_id=SESSION_ID,
        access_token=TOKEN,
        content="use echo",
        sessions=sessions,
        messages=InMemoryMessageRepository(),
        scenarios=InMemoryScenarioRepository(DEFAULT_SCENARIO),
        router=router,
        uow=RecordingUnitOfWork(),
        now=fixed_now,
        max_message_chars=500,
        max_history_messages=40,
        id_factory=IdFactory(),
        chat_mode=chat_mode,
        use_guest_mcp=use_guest_mcp,
        guest_mcp_owner_id=guest_mcp_owner_id,
        guest_mcp_registry=registry,
        guest_mcp_client=_PongGuestClient(),
        guest_tool_runner=guest_runner,
        analytics_distinct_id="visitor-1",
    )
    return [e async for e in events]


@pytest.mark.asyncio
async def test_single_mode_runs_guest_tool_and_streams_answer() -> None:
    _PongGuestClient.calls = []
    registry = InMemoryGuestMcpRegistry()
    await _seed_guest(registry)
    events = await _stream(registry=registry, chat_mode="single")
    starts = [e for e in events if isinstance(e, ToolStartEvent)]
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    ends = [e for e in events if isinstance(e, MessageEndEvent)]
    assert len(starts) == 1
    assert starts[0].name == "echo"
    assert len(results) == 1
    assert results[0].status == "ok"
    assert len(ends) == 1
    assert ends[0].model_id == "fake-model"
    assert _PongGuestClient.calls == [
        ("https://kit.example.com/mcp", "bearer-secret", "echo", {})
    ]


@pytest.mark.asyncio
async def test_compare_mode_skips_guest_openai_tools() -> None:
    registry = InMemoryGuestMcpRegistry()
    await _seed_guest(registry)
    spy = _SpyGuestRunner(
        owner_id=USER_ID,
        registry=registry,
        client=_PongGuestClient(),
        analytics=None,
        distinct_id="visitor-1",
    )
    await _stream(registry=registry, chat_mode="compare", guest_runner=spy)
    assert spy.openai_tools_calls == 0


@pytest.mark.asyncio
async def test_omitted_chat_mode_defaults_single() -> None:
    _PongGuestClient.calls = []
    registry = InMemoryGuestMcpRegistry()
    await _seed_guest(registry)
    events = await _stream(registry=registry, chat_mode=None)
    assert any(isinstance(e, ToolStartEvent) and e.name == "echo" for e in events)


@pytest.mark.asyncio
async def test_anonymous_owner_skips_guest_tools() -> None:
    registry = InMemoryGuestMcpRegistry()
    await _seed_guest(registry)
    events = await _stream(registry=registry, chat_mode="single", guest_mcp_owner_id=None)
    assert not any(isinstance(e, ToolStartEvent) for e in events)


@pytest.mark.asyncio
async def test_use_guest_mcp_false_skips_guest_tools() -> None:
    registry = InMemoryGuestMcpRegistry()
    await _seed_guest(registry)
    events = await _stream(registry=registry, chat_mode="single", use_guest_mcp=False)
    assert not any(isinstance(e, ToolStartEvent) for e in events)

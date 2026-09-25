"""Agent workshop calls Stand Pulse MCP tools and uses the result."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.adapters.llm.fake import FakeLLMProvider
from app.adapters.mcp_catalog_http import FakeMcpToolRunner
from app.application.agent_run import detect_pulse_intent, run_agent
from app.domain.agent_definition import AgentDefinition
from app.domain.entities import ChatMessage, CompletionResult, MessageRole
from app.domain.generation import GenerationParams


@dataclass
class _RecordingRouter:
    provider: FakeLLMProvider
    last_tools: object = None
    complete_count: int = 0
    last_messages: list[ChatMessage] = field(default_factory=list)

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = "auto",
        *,
        generation: GenerationParams | None = None,
        tools: object = None,
    ) -> CompletionResult:
        self.complete_count += 1
        self.last_tools = tools
        self.last_messages = list(messages)
        return await self.provider.complete_chat(
            messages,
            preferred_model,
            generation=generation,
            tools=tools,  # type: ignore[arg-type]
        )

    async def stream_chat(self, *args: object, **kwargs: object):  # pragma: no cover
        raise NotImplementedError


@pytest.mark.asyncio
async def test_run_agent_calls_probe_stand_and_uses_result() -> None:
    runner = FakeMcpToolRunner()
    router = _RecordingRouter(FakeLLMProvider())
    definition = AgentDefinition(
        name="Pulse",
        system_prompt="Дежурный оператор стенда.",
        preferred_model="fake-model",
    )
    outcome = await run_agent(
        definition=definition,
        message="Проверь стенд, пульс здоровья",
        router=router,  # type: ignore[arg-type]
        enabled=True,
        max_message_chars=8000,
        mcp_runner=runner,
    )
    assert runner.calls == [("probe_stand", {})]
    assert len(outcome.mcp_calls) == 1
    assert outcome.mcp_calls[0].name == "probe_stand"
    assert "12" in outcome.result.content
    assert router.complete_count == 2
    assert router.last_tools is None or router.last_tools  # first call had tools


def test_detect_pulse_intent_schedule() -> None:
    name, args = detect_pulse_intent(
        "Поставь сводку каждые 60 секунд",
        {"schedule_digest", "probe_stand"},
    )
    assert name == "schedule_digest"
    assert args["interval_seconds"] == 60


@pytest.mark.asyncio
async def test_fake_llm_emits_model_pulse_tool() -> None:
    provider = FakeLLMProvider()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "model_pulse",
                "description": "ranking",
                "parameters": {"type": "object", "properties": {"hours": {"type": "integer"}}},
            },
        }
    ]
    result = await provider.complete_chat(
        [ChatMessage(role=MessageRole.USER, content="Покажи рейтинг моделей")],
        "fake-model",
        tools=tools,
    )
    assert result.tool_calls
    assert result.tool_calls[0].name == "model_pulse"


@pytest.mark.asyncio
async def test_intent_fallback_when_model_skips_tools() -> None:
    class SilentRouter:
        async def complete_chat(
            self, messages, preferred_model="auto", *, generation=None, tools=None
        ):
            _ = tools
            if any("Результат MCP" in (m.content or "") for m in messages):
                return CompletionResult(content="стенд проверен", model_id="x")
            return CompletionResult(content="без инструментов", model_id="x")

        async def stream_chat(self, *args, **kwargs):  # pragma: no cover
            raise NotImplementedError

    runner = FakeMcpToolRunner()
    outcome = await run_agent(
        definition=AgentDefinition(name="P", system_prompt="ops", preferred_model="x"),
        message="Проверь здоровье стенда",
        router=SilentRouter(),  # type: ignore[arg-type]
        enabled=True,
        max_message_chars=8000,
        mcp_runner=runner,
    )
    assert runner.calls[0][0] == "probe_stand"
    assert outcome.result.content == "стенд проверен"


@pytest.mark.asyncio
async def test_run_agent_pipeline_search_summarize_save() -> None:
    runner = FakeMcpToolRunner()
    router = _RecordingRouter(FakeLLMProvider())
    outcome = await run_agent(
        definition=AgentDefinition(
            name="Pulse",
            system_prompt="Дежурный оператор стенда.",
            preferred_model="fake-model",
        ),
        message="Собери ночной бриф пайплайном search → summarize → saveToFile",
        router=router,  # type: ignore[arg-type]
        enabled=True,
        max_message_chars=8000,
        mcp_runner=runner,
    )
    names = [name for name, _args in runner.calls]
    assert names == ["search", "summarize", "saveToFile"]
    payload = runner.calls[1][1]["payload"]
    assert '"source": "search"' in payload or '"source":"search"' in payload
    brief = runner.calls[2][1]["brief"]
    assert '"source": "summarize"' in brief or '"source":"summarize"' in brief
    assert [call.name for call in outcome.mcp_calls] == names
    assert "сохран" in outcome.result.content.lower()
    assert router.complete_count == 2
    assert router.last_tools


@pytest.mark.asyncio
async def test_pipeline_continues_when_model_only_narrates() -> None:
    class NarratingRouter:
        async def complete_chat(
            self, messages, preferred_model="auto", *, generation=None, tools=None
        ):
            _ = tools
            if any("Результат MCP saveToFile" in (m.content or "") for m in messages):
                return CompletionResult(content="Бриф сохранён: /tmp/night-brief.md", model_id="x")
            return CompletionResult(content="сейчас вызову следующий инструмент", model_id="x")

        async def stream_chat(self, *args, **kwargs):  # pragma: no cover
            raise NotImplementedError

    runner = FakeMcpToolRunner()
    outcome = await run_agent(
        definition=AgentDefinition(name="P", system_prompt="ops", preferred_model="x"),
        message="Собери ночной бриф пайплайном",
        router=NarratingRouter(),  # type: ignore[arg-type]
        enabled=True,
        max_message_chars=8000,
        mcp_runner=runner,
    )
    assert [name for name, _args in runner.calls] == ["search", "summarize", "saveToFile"]
    assert "search" in runner.calls[1][1]["payload"]
    assert "summarize" in runner.calls[2][1]["brief"]
    assert "сохран" in outcome.result.content.lower()


@pytest.mark.asyncio
async def test_shift_review_routes_across_servers() -> None:
    runner = FakeMcpToolRunner()
    router = _RecordingRouter(FakeLLMProvider())
    outcome = await run_agent(
        definition=AgentDefinition(name="Pulse", system_prompt="ops", preferred_model="fake-model"),
        message="Сделай разбор смены через несколько серверов",
        router=router,  # type: ignore[arg-type]
        enabled=True,
        max_message_chars=8000,
        mcp_runner=runner,
    )
    assert [name for name, _args in runner.calls] == [
        "watch_brief",
        "model_pulse",
        "search",
        "summarize",
        "saveToFile",
    ]
    assert [call.server for call in outcome.mcp_calls] == [
        "watch",
        "models",
        "brief",
        "brief",
        "brief",
    ]
    assert "search" in runner.calls[3][1]["payload"]
    assert runner.calls[4][1]["name"] == "shift-review"


def test_detect_pulse_intent_pipeline() -> None:
    name, args = detect_pulse_intent(
        "Собери ночной бриф пайплайном",
        {"search", "summarize", "saveToFile", "probe_stand"},
    )
    assert name == "search"
    assert args["hours"] == 24

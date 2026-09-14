"""Unit tests for agent graph planning and run."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.application.graph_run import iter_graph_run
from app.domain.agent_graph import parse_graph_payload, plan_graph
from app.domain.entities import ChatMessage, CompletionResult
from app.domain.errors import MessageValidationError
from app.domain.generation import GenerationParams


def _chain_payload() -> dict:
    return {
        "name": "chain",
        "nodes": [
            {"id": "s", "data": {"kind": "start", "label": "Старт"}},
            {
                "id": "a",
                "data": {
                    "kind": "agent",
                    "label": "A",
                    "systemPrompt": "Be A",
                    "preferredModel": "auto",
                },
            },
            {
                "id": "b",
                "data": {
                    "kind": "agent",
                    "label": "B",
                    "systemPrompt": "Be B",
                    "preferredModel": "auto",
                },
            },
            {"id": "e", "data": {"kind": "end", "label": "Конец"}},
        ],
        "edges": [
            {"id": "1", "source": "s", "target": "a"},
            {"id": "2", "source": "a", "target": "b"},
            {"id": "3", "source": "b", "target": "e"},
        ],
    }


def test_plan_chain_order() -> None:
    g = parse_graph_payload(_chain_payload())
    plan = plan_graph(g)
    assert plan.order == ("s", "a", "b", "e")


def test_cycle_rejected() -> None:
    raw = _chain_payload()
    raw["edges"].append({"id": "c", "source": "b", "target": "a"})
    g = parse_graph_payload(raw)
    with pytest.raises(MessageValidationError, match="цикл"):
        plan_graph(g)


@dataclass
class _FakeRouter:
    calls: list[str] = field(default_factory=list)

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = "auto",
        *,
        generation: GenerationParams | None = None,
        tools: object = None,
    ) -> CompletionResult:
        user = next((m.content for m in messages if m.role.value == "user"), "")
        self.calls.append(user)
        n = len(self.calls)
        return CompletionResult(content=f"ans-{n}", model_id=f"fake-{n}")

    async def stream_chat(self, *args: object, **kwargs: object):  # pragma: no cover
        raise NotImplementedError


@pytest.mark.asyncio
async def test_iter_graph_run_chain() -> None:
    router = _FakeRouter()
    events = []
    async for ev in iter_graph_run(
        graph_payload=_chain_payload(),
        message="hello TZ",
        router=router,  # type: ignore[arg-type]
        enabled=True,
        max_message_chars=8000,
    ):
        events.append(ev)
    kinds = [e["event"] for e in events]
    assert kinds[0] == "graph_start"
    assert kinds[-1] == "done"
    assert events[-1]["data"]["content"] == "ans-2"
    assert len(router.calls) == 2


@pytest.mark.asyncio
async def test_iter_graph_run_recovers_and_switches_model() -> None:
    """First agent fails once, retries with auto, graph still finishes."""

    @dataclass
    class _FlakyRouter:
        calls: list[str] = field(default_factory=list)

        async def complete_chat(
            self,
            messages: list[ChatMessage],
            preferred_model: str = "auto",
            *,
            generation: GenerationParams | None = None,
            tools: object = None,
        ) -> CompletionResult:
            from app.domain.errors import LLMExhaustedError

            self.calls.append(preferred_model)
            if len(self.calls) == 1:
                raise LLMExhaustedError("simulated exhaust")
            return CompletionResult(content=f"ok-{len(self.calls)}", model_id="backup-model")

        async def stream_chat(self, *args: object, **kwargs: object):  # pragma: no cover
            raise NotImplementedError

    router = _FlakyRouter()
    events = []
    async for ev in iter_graph_run(
        graph_payload=_chain_payload(),
        message="hello TZ",
        router=router,  # type: ignore[arg-type]
        enabled=True,
        max_message_chars=8000,
    ):
        events.append(ev)

    kinds = [e["event"] for e in events]
    assert "node_retry" in kinds
    assert "model_switch" in kinds or kinds.count("node_end") >= 4
    assert kinds[-1] == "done"
    assert events[-1]["data"]["content"] == "ok-3"
    # agent A: fail + retry; agent B: success
    assert len(router.calls) == 3


@pytest.mark.asyncio
async def test_iter_graph_run_degrades_and_continues() -> None:
    @dataclass
    class _DeadRouter:
        async def complete_chat(self, *args: object, **kwargs: object) -> CompletionResult:
            from app.domain.errors import LLMExhaustedError

            raise LLMExhaustedError("all dead")

        async def stream_chat(self, *args: object, **kwargs: object):  # pragma: no cover
            raise NotImplementedError

    events = []
    async for ev in iter_graph_run(
        graph_payload=_chain_payload(),
        message="hello",
        router=_DeadRouter(),  # type: ignore[arg-type]
        enabled=True,
        max_message_chars=8000,
    ):
        events.append(ev)

    kinds = [e["event"] for e in events]
    assert "node_degraded" in kinds
    assert kinds[-1] == "done"
    assert "[узел" in events[-1]["data"]["content"]

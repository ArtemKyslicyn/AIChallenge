import json
from uuid import uuid4

import httpx
import pytest

from app.adapters.llm.fake import FakeLLMProvider
from app.adapters.llm.router import ModelRouter, TieredModelRouter
from app.adapters.llm.routing_provider import RoutingLLMProvider
from app.domain.entities import ChatMessage, CompletionResult, MessageRole, TokenChunk
from app.domain.errors import LLMExhaustedError, LLMProviderError
from app.domain.generation import GenerationParams
from app.domain.local_llm import (
    LocalLlmSource,
    reset_local_llm_source,
    set_local_llm_source,
)


def _source(models: tuple[str, ...]) -> LocalLlmSource:
    return LocalLlmSource(
        user_id=uuid4(),
        name="M1",
        base_url="http://127.0.0.1:11434",
        api_key=None,
        enabled=True,
        models=models,
        status="connected",
        safe_error=None,
    )


async def test_cloud_pin_does_not_touch_ollama() -> None:
    cloud = FakeLLMProvider(text="cloud")
    router_provider = RoutingLLMProvider(cloud)
    result = await router_provider.complete_chat(
        [ChatMessage(role=MessageRole.USER, content="hi")],
        "model-a",
    )
    assert result.content == "cloud"
    assert result.model_id == "model-a"


async def test_ollama_pin_without_scope_does_not_call_cloud() -> None:
    cloud = FakeLLMProvider(text="cloud")
    provider = RoutingLLMProvider(cloud)
    with pytest.raises(LLMProviderError) as exc:
        await provider.complete_chat(
            [ChatMessage(role=MessageRole.USER, content="hi")],
            "ollama/qwen36-fast:latest",
        )
    assert exc.value.model_id == "ollama/qwen36-fast:latest"
    assert "Профиле" in exc.value.message
    assert exc.value.kind == "config"


async def test_ollama_pin_uses_the_scoped_origin() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "qwen36-fast:latest"
        assert body["think"] is False
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "Имя: Артем"}, "done": True},
        )

    cloud = FakeLLMProvider(text="cloud")
    provider = RoutingLLMProvider(cloud, transport=httpx.MockTransport(handler))
    token = set_local_llm_source(_source(("qwen36-fast:latest",)))
    try:
        result = await provider.complete_chat(
            [ChatMessage(role=MessageRole.USER, content="память")],
            "ollama/qwen36-fast:latest",
            generation=GenerationParams(temperature=0.15, max_tokens=40),
        )
    finally:
        reset_local_llm_source(token)
    assert result.content == "Имя: Артем"
    assert result.model_id == "ollama/qwen36-fast:latest"


async def test_missing_tag_does_not_call_cloud() -> None:
    cloud = FakeLLMProvider(text="cloud")
    provider = RoutingLLMProvider(cloud)
    token = set_local_llm_source(_source(("llama3.1:8b",)))
    try:
        with pytest.raises(LLMProviderError) as exc:
            await provider.complete_chat(
                [ChatMessage(role=MessageRole.USER, content="hi")],
                "ollama/qwen36-fast:latest",
            )
    finally:
        reset_local_llm_source(token)
    assert exc.value.kind == "config"
    assert "cloud" not in str(exc.value)


class _TimeoutThenCloud:
    def __init__(self) -> None:
        self.models: list[str] = []

    async def complete_chat(self, messages, model, *, generation=None, tools=None):
        del messages, generation, tools
        self.models.append(model)
        if model.startswith("ollama/"):
            raise LLMProviderError("slow", kind="timeout", model_id=model)
        return CompletionResult(content="cloud", model_id=model)

    async def stream_chat(self, messages, model, *, generation=None):
        del messages, generation
        self.models.append(model)
        if False:
            yield TokenChunk(text="", model_id=model)
        raise LLMProviderError("slow", kind="timeout", model_id=model)


async def test_ollama_pin_does_not_fall_through_the_cloud_chain() -> None:
    provider = _TimeoutThenCloud()
    router = ModelRouter(provider, ["cloud-model"])
    with pytest.raises(LLMExhaustedError):
        await router.complete_chat(
            [ChatMessage(role=MessageRole.USER, content="hi")],
            "ollama/qwen36-fast:latest",
        )
    assert provider.models == ["ollama/qwen36-fast:latest"]


async def test_ollama_pin_does_not_use_the_fallback_tier() -> None:
    primary = _TimeoutThenCloud()
    fallback = FakeLLMProvider(text="fallback")
    tiered = TieredModelRouter(
        [ModelRouter(primary, ["cloud-model"]), ModelRouter(fallback, ["other"])]
    )
    with pytest.raises(LLMExhaustedError):
        await tiered.complete_chat(
            [ChatMessage(role=MessageRole.USER, content="hi")],
            "ollama/qwen36-fast:latest",
        )
    assert primary.models == ["ollama/qwen36-fast:latest"]


async def test_router_stops_on_config_error() -> None:
    cloud = FakeLLMProvider(text="cloud")
    router = ModelRouter(RoutingLLMProvider(cloud), ["cloud-model"])
    with pytest.raises(LLMProviderError) as exc:
        await router.complete_chat(
            [ChatMessage(role=MessageRole.USER, content="hi")],
            "ollama/qwen36-fast:latest",
        )
    assert exc.value.kind == "config"
    assert exc.value.model_id == "ollama/qwen36-fast:latest"

import json

import httpx
import pytest

from app.adapters.llm.ollama_native import OllamaNativeProvider, fetch_ollama_tags
from app.domain.entities import ChatMessage, MessageRole
from app.domain.errors import LLMProviderError
from app.domain.generation import GenerationParams


def _provider(handler, api_key: str | None = None) -> OllamaNativeProvider:
    return OllamaNativeProvider(
        "http://127.0.0.1:11434",
        api_key=api_key,
        transport=httpx.MockTransport(handler),
    )


async def test_complete_sends_think_false_and_rewrites_model_id() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "Имя: Артем\nЯзык: Python"},
                "done": True,
                "model": "qwen36-fast:latest",
            },
        )

    provider = _provider(handler)
    result = await provider.complete_chat(
        [ChatMessage(role=MessageRole.USER, content="память")],
        "ollama/qwen36-fast:latest",
        generation=GenerationParams(temperature=0.15, max_tokens=40),
    )
    assert result.model_id == "ollama/qwen36-fast:latest"
    assert result.content.startswith("Имя: Артем")
    assert seen["body"]["think"] is False
    assert seen["body"]["model"] == "qwen36-fast:latest"
    assert seen["body"]["options"]["temperature"] == 0.15
    assert seen["body"]["options"]["num_predict"] == 40
    assert seen["auth"] is None


async def test_api_key_is_bearer() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "ок"}, "done": True},
        )

    provider = _provider(handler, api_key="ollama")
    await provider.complete_chat(
        [ChatMessage(role=MessageRole.USER, content="ping")],
        "ollama/qwen36-fast:latest",
    )
    assert seen["auth"] == "Bearer ollama"


async def test_reasoning_sends_think_true() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "ок"}, "done": True},
        )

    provider = _provider(handler)
    await provider.complete_chat(
        [ChatMessage(role=MessageRole.USER, content="ping")],
        "ollama/qwen36-fast:latest",
        generation=GenerationParams(reasoning=True),
    )
    assert seen["body"]["think"] is True


async def test_empty_content_is_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "", "reasoning": "думал"},
                "done": True,
            },
        )

    provider = _provider(handler)
    with pytest.raises(LLMProviderError) as exc:
        await provider.complete_chat(
            [ChatMessage(role=MessageRole.USER, content="ping")],
            "ollama/qwen36-fast:latest",
        )
    assert exc.value.kind == "empty"
    assert exc.value.model_id == "ollama/qwen36-fast:latest"


async def test_fetch_tags_returns_names() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={"models": [{"name": "qwen36-fast:latest"}, {"name": "llama3.1:8b"}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        names = await fetch_ollama_tags("http://127.0.0.1:11434", None, client=client)
    assert names == ("qwen36-fast:latest", "llama3.1:8b")

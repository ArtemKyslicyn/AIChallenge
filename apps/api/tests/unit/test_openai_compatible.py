import httpx
import pytest

from app.adapters.llm.openai_compatible import OpenAICompatibleProvider
from app.domain.entities import ChatMessage, MessageRole
from app.domain.errors import LLMProviderError

USER_TURN = [ChatMessage(role=MessageRole.USER, content="x")]

SSE_BODY = (
    b'data: {"model":"served-model","choices":[{"delta":{"content":"He"}}]}\n\n'
    b'data: {"choices":[{"delta":{}}]}\n\n'
    b"data: not-json\n\n"
    b'data: {"model":"served-model","choices":[{"delta":{"content":"llo"}}]}\n\n'
    b"data: [DONE]\n\n"
)


def _provider(handler: object) -> OpenAICompatibleProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return OpenAICompatibleProvider("https://provider.test/v1", "unused", client=client)


async def test_stream_parses_sse_and_skips_noise() -> None:
    provider = _provider(lambda request: httpx.Response(200, content=SSE_BODY))
    chunks = [c async for c in provider.stream_chat(USER_TURN, "requested-model")]
    assert "".join(c.text for c in chunks) == "Hello"
    # The model the provider says it used wins over the one we asked for.
    assert {c.model_id for c in chunks} == {"served-model"}


async def test_stream_maps_429_to_retryable_provider_error() -> None:
    provider = _provider(lambda request: httpx.Response(429, json={"error": "slow down"}))
    with pytest.raises(LLMProviderError) as exc:
        _ = [c async for c in provider.stream_chat(USER_TURN, "model-a")]
    assert exc.value.status == 429
    assert exc.value.model_id == "model-a"
    assert "slow down" not in str(exc.value)


async def test_complete_returns_content_and_served_model() -> None:
    body = {"model": "served-model", "choices": [{"message": {"content": "hi"}}]}
    provider = _provider(lambda request: httpx.Response(200, json=body))
    result = await provider.complete_chat(USER_TURN, "requested-model")
    assert result.content == "hi"
    assert result.model_id == "served-model"


async def test_timeout_is_reported_as_retryable_kind() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow", request=request)

    provider = _provider(boom)
    with pytest.raises(LLMProviderError) as exc:
        await provider.complete_chat(USER_TURN, "model-a")
    assert exc.value.kind == "timeout"


async def test_malformed_body_is_not_retryable() -> None:
    provider = _provider(lambda request: httpx.Response(200, json={"nope": True}))
    with pytest.raises(LLMProviderError) as exc:
        await provider.complete_chat(USER_TURN, "model-a")
    assert exc.value.kind == "malformed"
    assert exc.value.status is None

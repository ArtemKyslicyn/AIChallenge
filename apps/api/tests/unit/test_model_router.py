import asyncio

import pytest

from app.adapters.llm.fake import FakeLLMProvider, FlakyLLMProvider
from app.adapters.llm.router import ModelRouter
from app.domain.entities import ChatMessage, CompletionResult, MessageRole, TokenChunk
from app.domain.errors import LLMExhaustedError, LLMProviderError, LLMStreamAbortedError

USER_TURN = [ChatMessage(role=MessageRole.USER, content="x")]


async def test_router_failsover_and_reports_second_model() -> None:
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=429, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    result = await router.complete_chat(USER_TURN, preferred_model="auto")
    assert result.model_id == "model-b"
    assert result.content == "hi"


async def test_fake_stream_emits_model_id() -> None:
    provider = FakeLLMProvider(text="ab", model_id="fake-1")
    chunks = [c async for c in provider.stream_chat([], model="fake-1")]
    assert "".join(c.text for c in chunks) == "ab"
    assert all(c.model_id == "fake-1" for c in chunks)


async def test_stream_failsover_before_first_token() -> None:
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=429, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    chunks = [c async for c in router.stream_chat(USER_TURN, preferred_model="auto")]
    assert "".join(c.text for c in chunks) == "hi"
    assert {c.model_id for c in chunks} == {"model-b"}


async def test_stream_does_not_failover_after_first_token() -> None:
    # model-a yields "he", then dies with 429 — the router must NOT continue on model-b,
    # because splicing two completions produces incoherent text.
    provider = FlakyLLMProvider(fail_mid_stream={"model-a"}, partial_text="he", ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    seen = []
    with pytest.raises(LLMStreamAbortedError) as exc:
        async for chunk in router.stream_chat(USER_TURN, preferred_model="auto"):
            seen.append(chunk)
    assert "".join(c.text for c in seen) == "he"
    assert exc.value.model_id == "model-a"
    assert exc.value.partial_text == "he"


async def test_exhausted_model_recovers_after_ttl() -> None:
    clock = {"t": 0.0}
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=429, ok_text="hi")
    router = ModelRouter(
        provider,
        ["model-a", "model-b"],
        exhausted_ttl_seconds=300,
        now=lambda: clock["t"],
    )
    assert (await router.complete_chat(USER_TURN)).model_id == "model-b"

    provider.fail_models.clear()
    clock["t"] = 301.0
    assert (await router.complete_chat(USER_TURN)).model_id == "model-a"


async def test_whole_chain_exhausted_raises() -> None:
    provider = FlakyLLMProvider(fail_models={"model-a", "model-b"}, fail_status=429)
    router = ModelRouter(provider, ["model-a", "model-b"])
    with pytest.raises(LLMExhaustedError):
        await router.complete_chat(USER_TURN)


async def test_preferred_model_is_pinned_first() -> None:
    provider = FlakyLLMProvider(ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    result = await router.complete_chat(USER_TURN, preferred_model="model-b")
    assert result.model_id == "model-b"


async def test_pinned_model_falls_back_when_it_fails() -> None:
    provider = FlakyLLMProvider(fail_models={"model-b"}, fail_status=402, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    result = await router.complete_chat(USER_TURN, preferred_model="model-b")
    assert result.model_id == "model-a"


async def test_stream_moves_on_when_a_model_returns_no_answer() -> None:
    # Reasoning-only responses cost the reader nothing, so failover is allowed.
    provider = FlakyLLMProvider(empty_models={"model-a"}, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    chunks = [c async for c in router.stream_chat(USER_TURN, preferred_model="auto")]
    assert "".join(c.text for c in chunks) == "hi"
    assert {c.model_id for c in chunks} == {"model-b"}


async def test_complete_moves_on_when_a_model_returns_no_answer() -> None:
    provider = FlakyLLMProvider(empty_models={"model-a"}, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    assert (await router.complete_chat(USER_TURN)).model_id == "model-b"


async def test_rejected_credentials_are_not_retried_down_the_chain() -> None:
    # A bad key is not a "this model is busy" condition: surface it as-is
    # instead of burning the chain and reporting "no model is available".
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=401, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])

    with pytest.raises(LLMProviderError) as exc:
        await router.complete_chat(USER_TURN)
    assert exc.value.status == 401

    # model-b must stay usable — it was never tried, so never marked exhausted.
    assert (await router.complete_chat(USER_TURN, preferred_model="model-b")).model_id == "model-b"


async def test_region_block_still_moves_to_the_next_model() -> None:
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=403, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    assert (await router.complete_chat(USER_TURN)).model_id == "model-b"


async def test_missing_model_404_moves_to_the_next_model() -> None:
    # OpenRouter free ids disappear often; 404 must not abort the whole reply.
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=404, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    assert (await router.complete_chat(USER_TURN)).model_id == "model-b"


async def test_gateway_blip_502_moves_to_the_next_model() -> None:
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=502, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    chunks = [c async for c in router.stream_chat(USER_TURN)]
    assert "".join(c.text for c in chunks) == "hi"
    assert {c.model_id for c in chunks} == {"model-b"}


class SlowFirstTokenProvider:
    """Answers instantly for some models and stalls before the first token for others."""

    def __init__(self, slow_models: set[str], delay: float, text: str = "hi") -> None:
        self.slow_models = slow_models
        self.delay = delay
        self.text = text

    async def stream_chat(self, messages: list[ChatMessage], model: str, **_: object):
        if model in self.slow_models:
            await asyncio.sleep(self.delay)
        yield TokenChunk(text=self.text, model_id=model)

    async def complete_chat(
        self, messages: list[ChatMessage], model: str, **_: object
    ) -> CompletionResult:
        if model in self.slow_models:
            await asyncio.sleep(self.delay)
        return CompletionResult(content=self.text, model_id=model)


async def test_a_model_that_thinks_too_long_loses_its_turn() -> None:
    provider = SlowFirstTokenProvider(slow_models={"model-a"}, delay=5)
    router = ModelRouter(provider, ["model-a", "model-b"], first_token_timeout_seconds=0.05)
    chunks = [c async for c in router.stream_chat(USER_TURN)]
    assert {c.model_id for c in chunks} == {"model-b"}


async def test_the_first_token_budget_does_not_cut_off_an_answer_in_progress() -> None:
    # The bound applies to starting, not to finishing: a model already writing
    # must be allowed to finish.
    provider = FakeLLMProvider(text="one two three", delay_seconds=0.02)
    router = ModelRouter(provider, ["model-a"], first_token_timeout_seconds=0.05)
    chunks = [c async for c in router.stream_chat(USER_TURN)]
    assert "".join(c.text for c in chunks) == "one two three"


async def test_one_request_tries_at_most_max_attempts_models() -> None:
    provider = FlakyLLMProvider(
        fail_models={"m1", "m2", "m3", "m4", "m5"}, fail_status=429, ok_text="hi"
    )
    router = ModelRouter(provider, ["m1", "m2", "m3", "m4", "m5"], max_attempts=3)

    with pytest.raises(LLMExhaustedError):
        await router.complete_chat(USER_TURN)

    # Only the first three were tried, so m4 and m5 are still fresh.
    provider.fail_models.clear()
    assert (await router.complete_chat(USER_TURN)).model_id == "m4"

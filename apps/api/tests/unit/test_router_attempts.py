"""The attempt journal: who was tried for one request, and how it went.

The collector is passed in per request rather than kept on the router, because
one ModelRouter instance serves every concurrent SSE stream in the process.
"""

import asyncio

import pytest

from app.adapters.llm.fake import FakeLLMProvider, FlakyLLMProvider
from app.adapters.llm.router import ModelRouter, TieredModelRouter
from app.domain.entities import ChatMessage, MessageRole
from app.domain.errors import LLMExhaustedError, LLMProviderError, LLMStreamAbortedError
from app.domain.tracing import AttemptRecord

USER_TURN = [ChatMessage(role=MessageRole.USER, content="x")]


async def test_stream_records_the_failed_model_and_the_one_that_answered() -> None:
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=429, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    attempts: list[AttemptRecord] = []

    chunks = [c async for c in router.stream_chat(USER_TURN, attempts=attempts)]

    assert "".join(c.text for c in chunks) == "hi"
    assert [(a.model_id, a.ok, a.reason) for a in attempts] == [
        ("model-a", False, "http_429"),
        ("model-b", True, ""),
    ]
    assert attempts[0].ttft_ms is None
    assert attempts[1].ttft_ms is not None


async def test_stream_ttft_is_measured_from_the_attempt_start() -> None:
    clock = {"t": 0.0}

    class SlowFirstToken(FakeLLMProvider):
        async def stream_chat(self, messages, model, **kw):  # type: ignore[no-untyped-def]
            clock["t"] += 1.25
            async for chunk in super().stream_chat(messages, model):
                yield chunk

    router = ModelRouter(SlowFirstToken(text="hi"), ["model-a"], now=lambda: clock["t"])
    attempts: list[AttemptRecord] = []
    [c async for c in router.stream_chat(USER_TURN, attempts=attempts)]

    assert [a.ttft_ms for a in attempts] == [1250]


async def test_stream_records_the_error_kind_for_a_retryable_failure() -> None:
    provider = FlakyLLMProvider(empty_models={"model-a"}, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    attempts: list[AttemptRecord] = []

    [c async for c in router.stream_chat(USER_TURN, attempts=attempts)]

    assert attempts[0].error_kind == "empty"
    assert attempts[0].reason == "empty"


async def test_mid_stream_abort_is_journalled_as_a_failed_attempt() -> None:
    provider = FlakyLLMProvider(fail_mid_stream={"model-a"}, partial_text="he", ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    attempts: list[AttemptRecord] = []

    with pytest.raises(LLMStreamAbortedError):
        async for _ in router.stream_chat(USER_TURN, attempts=attempts):
            pass

    # One record for the attempt, not two: the first token started the clock,
    # the abort decided the verdict.
    assert [(a.model_id, a.ok, a.reason) for a in attempts] == [("model-a", False, "aborted")]
    assert attempts[0].ttft_ms is not None


async def test_exhausted_chain_journals_every_model_it_burned() -> None:
    provider = FlakyLLMProvider(fail_models={"model-a", "model-b"}, fail_status=429)
    router = ModelRouter(provider, ["model-a", "model-b"])
    attempts: list[AttemptRecord] = []

    with pytest.raises(LLMExhaustedError):
        async for _ in router.stream_chat(USER_TURN, attempts=attempts):
            pass

    assert [a.model_id for a in attempts] == ["model-a", "model-b"]
    assert not any(a.ok for a in attempts)


async def test_fatal_failure_is_not_journalled_as_a_model_verdict() -> None:
    # 401 says the credential is wrong, not that the model is slow or flaky.
    # Recording it would poison the model's aggregates for a config mistake.
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=401)
    router = ModelRouter(provider, ["model-a", "model-b"])
    attempts: list[AttemptRecord] = []

    with pytest.raises(LLMProviderError):
        async for _ in router.stream_chat(USER_TURN, attempts=attempts):
            pass

    assert attempts == []


async def test_complete_chat_records_attempts_too() -> None:
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=429, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    attempts: list[AttemptRecord] = []

    result = await router.complete_chat(USER_TURN, attempts=attempts)

    assert result.model_id == "model-b"
    assert [(a.model_id, a.ok) for a in attempts] == [("model-a", False), ("model-b", True)]


async def test_router_still_works_without_a_collector() -> None:
    # llm_probe and the media probe call the router with no journal at all.
    provider = FakeLLMProvider(text="hi")
    router = ModelRouter(provider, ["model-a"])
    assert (await router.complete_chat(USER_TURN)).content == "hi"
    assert [c async for c in router.stream_chat(USER_TURN)]


async def test_tiered_router_merges_both_tiers_into_one_journal() -> None:
    tier_one = ModelRouter(FlakyLLMProvider(fail_models={"model-a"}, fail_status=429), ["model-a"])
    tier_two = ModelRouter(FlakyLLMProvider(ok_text="hi"), ["model-b"])
    router = TieredModelRouter([tier_one, tier_two])
    attempts: list[AttemptRecord] = []

    chunks = [c async for c in router.stream_chat(USER_TURN, attempts=attempts)]

    assert "".join(c.text for c in chunks) == "hi"
    assert [(a.model_id, a.ok) for a in attempts] == [("model-a", False), ("model-b", True)]


async def test_concurrent_requests_keep_separate_journals() -> None:
    """The reason the collector is a parameter and not router state."""
    provider = FakeLLMProvider(text="hi", delay_seconds=0.01)
    router = ModelRouter(provider, ["model-a"])
    first: list[AttemptRecord] = []
    second: list[AttemptRecord] = []

    async def drain(collector: list[AttemptRecord]) -> None:
        async for _ in router.stream_chat(USER_TURN, attempts=collector):
            pass

    await asyncio.gather(drain(first), drain(second))

    assert len(first) == 1
    assert len(second) == 1

"""A badly-rated model goes to the back of the chain — and stays in it."""

from datetime import UTC, datetime

import pytest
from fakes import StubFeedbackStats

from app.adapters.api.sessions import _refresh_penalties
from app.adapters.llm.fake import FakeLLMProvider, FlakyLLMProvider
from app.adapters.llm.feedback_penalties import FeedbackPenaltyCache
from app.adapters.llm.router import ModelRouter
from app.domain.entities import ChatMessage, MessageRole
from app.domain.feedback import ModelFeedbackStats

USER_TURN = [ChatMessage(role=MessageRole.USER, content="x")]
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


async def penalizing(*model_ids: str) -> FeedbackPenaltyCache:
    """A cache already refreshed into penalizing exactly these models."""
    cache = FeedbackPenaltyCache(
        min_votes=5,
        down_rate_threshold=0.6,
        window_seconds=86400,
        refresh_seconds=60,
        now=lambda: NOW,
    )
    await cache.refresh(
        StubFeedbackStats(*(ModelFeedbackStats(model_id=m, ups=0, downs=9) for m in model_ids))
    )
    assert cache.penalized == frozenset(model_ids)
    return cache


def router(chain: list[str], penalties: FeedbackPenaltyCache | None = None) -> ModelRouter:
    return ModelRouter(FakeLLMProvider(text="hi"), chain, penalties=penalties)


async def test_without_a_cache_the_chain_is_untouched() -> None:
    assert router(["a", "b"])._candidates() == ["a", "b"]


async def test_a_penalized_model_moves_to_the_back() -> None:
    chain = router(["a", "b", "c"], await penalizing("a"))
    assert chain._candidates() == ["b", "c", "a"]


async def test_a_penalized_model_is_demoted_not_dropped() -> None:
    # The whole point of the soft penalty: a chain of one bad model still answers.
    chain = router(["a"], await penalizing("a"))
    assert chain._candidates() == ["a"]


async def test_demotion_keeps_the_relative_order_of_both_groups() -> None:
    chain = router(["a", "b", "c", "d"], await penalizing("a", "c"))
    assert chain._candidates() == ["b", "d", "a", "c"]


async def test_an_explicit_pin_stays_first_even_when_penalized() -> None:
    # Naming a model is an override; reordering around it would be a lie.
    chain = router(["a", "b"], await penalizing("a"))
    assert chain._candidates("a") == ["a", "b"]


async def test_a_pin_does_not_rescue_a_different_penalized_model() -> None:
    chain = router(["a", "b", "c"], await penalizing("b"))
    assert chain._candidates("c") == ["c", "a", "b"]


async def test_penalizing_everything_leaves_the_chain_in_its_own_order() -> None:
    chain = router(["a", "b"], await penalizing("a", "b"))
    assert chain._candidates() == ["a", "b"]


async def test_the_stream_actually_answers_from_the_promoted_model() -> None:
    provider = FakeLLMProvider(text="hi")
    chain = ModelRouter(provider, ["a", "b"], penalties=await penalizing("a"))
    chunks = [c async for c in chain.stream_chat(USER_TURN)]
    assert {c.model_id for c in chunks} == {"b"}


async def test_demotion_stacks_with_failover_rather_than_replacing_it() -> None:
    # "b" is preferred by the bias but broken; the chain still reaches "a".
    provider = FlakyLLMProvider(fail_models={"b"}, fail_status=429, ok_text="hi")
    chain = ModelRouter(provider, ["a", "b"], penalties=await penalizing("a"))
    result = await chain.complete_chat(USER_TURN)
    assert result.model_id == "a"


async def test_exhaustion_still_wins_over_the_bias() -> None:
    # Availability is a harder constraint than reputation: an exhausted model
    # is gone from the list entirely, penalized or not.
    clock = {"t": 0.0}
    provider = FlakyLLMProvider(fail_models={"b"}, fail_status=429, ok_text="hi")
    chain = ModelRouter(
        provider, ["a", "b"], now=lambda: clock["t"], penalties=await penalizing("a")
    )
    assert (await chain.complete_chat(USER_TURN)).model_id == "a"
    assert chain._candidates() == ["a"]


@pytest.mark.parametrize("pin", ["", "auto"])
async def test_no_pin_is_no_pin(pin: str) -> None:
    chain = router(["a", "b"], await penalizing("a"))
    assert chain._candidates(pin) == ["b", "a"]


class FakeResult:
    def all(self) -> list[object]:
        return []


class FakeDb:
    """Just enough AsyncSession for the repository's one SELECT."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.rollbacks = 0
        self.queries = 0

    async def execute(self, statement: object) -> FakeResult:
        self.queries += 1
        if self.fail:
            raise RuntimeError("connection is gone")
        return FakeResult()

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeContainer:
    def __init__(self, penalties: FeedbackPenaltyCache) -> None:
        self.penalties = penalties


async def test_the_chat_route_refreshes_the_bias_before_streaming() -> None:
    cache = FeedbackPenaltyCache(
        min_votes=5, down_rate_threshold=0.6, window_seconds=86400, refresh_seconds=60
    )
    db = FakeDb()

    await _refresh_penalties(FakeContainer(cache), db)  # type: ignore[arg-type]

    # The read really happened; nothing in it was bad enough to penalize.
    assert db.queries == 1
    assert cache.penalized == frozenset()


async def test_a_broken_refresh_never_blocks_the_chat() -> None:
    # The user's message is written through this same session moments later, so
    # the failed statement has to be rolled back, not just logged.
    cache = FeedbackPenaltyCache(
        min_votes=5, down_rate_threshold=0.6, window_seconds=86400, refresh_seconds=60
    )
    db = FakeDb(fail=True)

    await _refresh_penalties(FakeContainer(cache), db)  # type: ignore[arg-type]

    assert db.queries == 1
    assert db.rollbacks == 1

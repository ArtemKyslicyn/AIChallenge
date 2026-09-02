import pytest

from app.adapters.llm.fake import FlakyLLMProvider
from app.adapters.llm.router import ModelRouter, TieredModelRouter
from app.domain.entities import ChatMessage, MessageRole
from app.domain.errors import LLMExhaustedError, LLMProviderError

USER_TURN = [ChatMessage(role=MessageRole.USER, content="x")]


async def test_tiered_router_falls_back_when_primary_tier_auth_fails() -> None:
    primary = ModelRouter(
        FlakyLLMProvider(fail_models={"free-a"}, fail_status=401),
        ["free-a"],
    )
    fallback = ModelRouter(
        FlakyLLMProvider(ok_text="paid"),
        ["paid-a"],
    )
    router = TieredModelRouter([primary, fallback])
    result = await router.complete_chat(USER_TURN)
    assert result.model_id == "paid-a"
    assert result.content == "paid"


async def test_tiered_router_falls_back_to_second_provider() -> None:
    primary = ModelRouter(
        FlakyLLMProvider(fail_models={"free-a"}, fail_status=429, ok_text="nope"),
        ["free-a"],
    )
    fallback = ModelRouter(
        FlakyLLMProvider(ok_text="paid"),
        ["paid-a"],
    )
    router = TieredModelRouter([primary, fallback])
    result = await router.complete_chat(USER_TURN)
    assert result.model_id == "paid-a"
    assert result.content == "paid"


async def test_tiered_router_falls_back_after_primary_404s() -> None:
    primary = ModelRouter(
        FlakyLLMProvider(fail_models={"free-a", "free-b"}, fail_status=404),
        ["free-a", "free-b"],
    )
    fallback = ModelRouter(FlakyLLMProvider(ok_text="paid"), ["paid-a"])
    router = TieredModelRouter([primary, fallback])
    chunks = [c async for c in router.stream_chat(USER_TURN)]
    assert "".join(c.text for c in chunks) == "paid"
    assert {c.model_id for c in chunks} == {"paid-a"}


async def test_tiered_router_raises_when_all_tiers_exhausted() -> None:
    primary = ModelRouter(
        FlakyLLMProvider(fail_models={"free-a"}, fail_status=429),
        ["free-a"],
    )
    fallback = ModelRouter(
        FlakyLLMProvider(fail_models={"paid-a"}, fail_status=402),
        ["paid-a"],
    )
    router = TieredModelRouter([primary, fallback])
    with pytest.raises(LLMExhaustedError):
        await router.complete_chat(USER_TURN)


async def test_tiered_router_does_not_swallow_other_provider_errors() -> None:
    # Only a rejected credential disqualifies a tier. A broken response is a
    # real failure and must surface instead of quietly costing another provider.
    broken = ModelRouter(FlakyLLMProvider(fail_models={"free-a"}, fail_status=418), ["free-a"])
    fallback = ModelRouter(FlakyLLMProvider(ok_text="paid"), ["paid-a"])

    router = TieredModelRouter([broken, fallback])
    with pytest.raises(LLMProviderError) as exc:
        await router.complete_chat(USER_TURN)
    assert exc.value.status == 418


async def test_tiered_router_streams_and_falls_back_on_rejected_credential() -> None:
    primary = ModelRouter(FlakyLLMProvider(fail_models={"free-a"}, fail_status=401), ["free-a"])
    fallback = ModelRouter(FlakyLLMProvider(ok_text="paid"), ["paid-a"])
    router = TieredModelRouter([primary, fallback])

    chunks = [c async for c in router.stream_chat(USER_TURN)]
    assert "".join(c.text for c in chunks) == "paid"
    assert {c.model_id for c in chunks} == {"paid-a"}

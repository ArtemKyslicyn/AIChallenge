from app.adapters.llm.fake import FakeLLMProvider
from app.adapters.llm.router import ModelRouter
from app.application.llm_probe import complete_probe
from app.domain.entities import ChatMessage, MessageRole
from app.domain.generation import GenerationParams, PromptControlFlags

TURN = [ChatMessage(role=MessageRole.USER, content="ping")]


def _router() -> tuple[ModelRouter, FakeLLMProvider]:
    provider = FakeLLMProvider(text="pong")
    return ModelRouter(provider, ["model-a"]), provider


async def test_probe_passes_generation_to_provider() -> None:
    router, provider = _router()
    generation = GenerationParams(
        temperature=0.2,
        prompt_controls=PromptControlFlags(format=True),
    )
    await complete_probe(
        router=router,
        messages=TURN,
        enabled=True,
        generation=generation,
    )
    assert provider.last_generation is not None
    assert provider.last_generation.temperature == 0.2


async def test_probe_without_generation_leaves_provider_unset() -> None:
    router, provider = _router()
    await complete_probe(router=router, messages=TURN, enabled=True)
    assert provider.last_generation is None

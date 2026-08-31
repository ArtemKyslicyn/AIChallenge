import pytest

from app.adapters.llm.fake import FakeLLMProvider
from app.adapters.llm.router import ModelRouter
from app.application.llm_probe import complete_probe
from app.domain.entities import ChatMessage, MessageRole
from app.domain.errors import ProbeDisabledError

TURN = [ChatMessage(role=MessageRole.USER, content="ping")]


def _router() -> ModelRouter:
    return ModelRouter(FakeLLMProvider(text="pong"), ["model-a", "model-b"])


async def test_probe_returns_result_with_model_id() -> None:
    result = await complete_probe(router=_router(), messages=TURN, enabled=True)
    assert result.content == "pong"
    assert result.model_id == "model-a"


async def test_probe_honours_preferred_model() -> None:
    result = await complete_probe(
        router=_router(), messages=TURN, preferred_model="model-b", enabled=True
    )
    assert result.model_id == "model-b"


async def test_probe_rejected_when_disabled() -> None:
    with pytest.raises(ProbeDisabledError):
        await complete_probe(router=_router(), messages=TURN, enabled=False)

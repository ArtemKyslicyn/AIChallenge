"""Keyless providers used by tests, CI, and the USE_FAKE_LLM demo path."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterable

from app.domain.entities import ChatMessage, CompletionResult, TokenChunk
from app.domain.errors import LLMProviderError

_WORDS = re.compile(r"\S+\s*")

DEFAULT_FAKE_MODEL_ID = "fake-model"


def _split(text: str) -> list[str]:
    """Split into word-sized chunks so a stream looks like a real one."""
    return _WORDS.findall(text) or ([text] if text else [])


class FakeLLMProvider:
    """Deterministic provider so nothing in the test suite needs an API key.

    ``model_id`` overrides the reported model; left unset, the provider echoes
    back whichever model the router asked for, which is what keeps the chain
    meaningful in the keyless demo path.
    """

    def __init__(
        self, text: str = "Это детерминированный тестовый ответ.", model_id: str | None = None
    ) -> None:
        self.text = text
        self.model_id = model_id

    def _resolve(self, model: str) -> str:
        return self.model_id or model or DEFAULT_FAKE_MODEL_ID

    async def stream_chat(
        self, messages: list[ChatMessage], model: str
    ) -> AsyncIterator[TokenChunk]:
        model_id = self._resolve(model)
        for piece in _split(self.text):
            yield TokenChunk(text=piece, model_id=model_id)

    async def complete_chat(self, messages: list[ChatMessage], model: str) -> CompletionResult:
        return CompletionResult(content=self.text, model_id=self._resolve(model))


class FlakyLLMProvider:
    """Test double that fails on demand, either before or after the first token.

    ``fail_models`` fail before yielding anything (the router may fail over).
    ``fail_mid_stream`` yield ``partial_text`` first and then fail (the router
    must not fail over).
    """

    def __init__(
        self,
        *,
        fail_models: Iterable[str] | None = None,
        fail_status: int = 429,
        ok_text: str = "ok",
        fail_mid_stream: Iterable[str] | None = None,
        partial_text: str = "",
    ) -> None:
        self.fail_models = set(fail_models or ())
        self.fail_mid_stream = set(fail_mid_stream or ())
        self.fail_status = fail_status
        self.ok_text = ok_text
        self.partial_text = partial_text

    def _boom(self, model: str) -> LLMProviderError:
        return LLMProviderError(
            "provider rejected the request", status=self.fail_status, model_id=model
        )

    async def stream_chat(
        self, messages: list[ChatMessage], model: str
    ) -> AsyncIterator[TokenChunk]:
        if model in self.fail_models:
            raise self._boom(model)
        if model in self.fail_mid_stream:
            for piece in _split(self.partial_text):
                yield TokenChunk(text=piece, model_id=model)
            raise self._boom(model)
        for piece in _split(self.ok_text):
            yield TokenChunk(text=piece, model_id=model)

    async def complete_chat(self, messages: list[ChatMessage], model: str) -> CompletionResult:
        if model in self.fail_models:
            raise self._boom(model)
        return CompletionResult(content=self.ok_text, model_id=model)

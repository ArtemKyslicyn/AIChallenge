"""Keyless providers used by tests, CI, and the USE_FAKE_LLM demo path."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Iterable

from app.domain.entities import ChatMessage, CompletionResult, TokenChunk
from app.domain.errors import LLMProviderError
from app.domain.generation import GenerationParams
from app.domain.media import IMAGE_TOOL_NAME, ToolCallRequest

_WORDS = re.compile(r"\S+\s*")

DEFAULT_FAKE_MODEL_ID = "fake-model"

#: The keyless demo answer. Deliberately Markdown: it is what shows the
#: renderer working when no provider key is configured.
DEMO_ANSWER = """### Пример ответа

Модель отвечает **Markdown**, и он рендерится по ходу стрима.

- списки и `инлайн-код`
- таблицы
- блоки кода с копированием

```python
def greet(name: str) -> str:
    return f"Привет, {name}!"
```

| Поле | Значение |
| --- | --- |
| Провайдер | fake |
| Стриминг | да |
"""


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
        self,
        text: str = DEMO_ANSWER,
        model_id: str | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.text = text
        self.model_id = model_id
        #: Pause between chunks. Tests that need a stream still running when the
        #: client hangs up set this; the default answers in one go.
        self.delay_seconds = delay_seconds
        self.last_generation: GenerationParams | None = None

    def _resolve(self, model: str) -> str:
        return self.model_id or model or DEFAULT_FAKE_MODEL_ID

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None = None,
    ) -> AsyncIterator[TokenChunk]:
        model_id = self._resolve(model)
        for piece in _split(self.text):
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            yield TokenChunk(text=piece, model_id=model_id)

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> CompletionResult:
        self.last_generation = generation
        if tools:
            last = next((m.content for m in reversed(messages) if m.content), "")
            if "TOOL_IMAGE:" in last:
                prompt = last.split("TOOL_IMAGE:", 1)[1].strip() or "test"
                return CompletionResult(
                    content="",
                    model_id=self._resolve(model),
                    tool_calls=[
                        ToolCallRequest(
                            id="fake-tool-1",
                            name=IMAGE_TOOL_NAME,
                            arguments={"prompt": prompt, "model": "flux"},
                        )
                    ],
                )
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
        empty_models: Iterable[str] | None = None,
        partial_text: str = "",
    ) -> None:
        self.fail_models = set(fail_models or ())
        self.fail_mid_stream = set(fail_mid_stream or ())
        #: Models that answer with no content at all, the way a reasoning model
        #: does when it runs out of budget before writing an answer.
        self.empty_models = set(empty_models or ())
        self.fail_status = fail_status
        self.ok_text = ok_text
        self.partial_text = partial_text

    @staticmethod
    def _empty(model: str) -> LLMProviderError:
        return LLMProviderError("no answer content", kind="empty", model_id=model)

    def _boom(self, model: str) -> LLMProviderError:
        return LLMProviderError(
            "provider rejected the request", status=self.fail_status, model_id=model
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None = None,
    ) -> AsyncIterator[TokenChunk]:
        if model in self.fail_models:
            raise self._boom(model)
        if model in self.empty_models:
            raise self._empty(model)
        if model in self.fail_mid_stream:
            for piece in _split(self.partial_text):
                yield TokenChunk(text=piece, model_id=model)
            raise self._boom(model)
        for piece in _split(self.ok_text):
            yield TokenChunk(text=piece, model_id=model)

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> CompletionResult:
        _ = tools
        if model in self.fail_models:
            raise self._boom(model)
        if model in self.empty_models:
            raise self._empty(model)
        return CompletionResult(content=self.ok_text, model_id=model)

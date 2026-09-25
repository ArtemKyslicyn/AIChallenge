"""Keyless providers used by tests, CI, and the USE_FAKE_LLM demo path."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Iterable

from app.domain.entities import ChatMessage, CompletionResult, TokenChunk
from app.domain.errors import LLMProviderError
from app.domain.generation import GenerationParams
from app.domain.media import IMAGE_TOOL_NAME, ToolCallRequest

_WORDS = re.compile(r"\S+\s*")
_PULSE_HINT = re.compile(
    r"(?i)пульс|здоров|health|рейтинг|сводк|digest|probe_stand|model_pulse|"
    r"ranking|расписан|schedule|pareto|статус стенда|проверь стенд|"
    r"вахт|инцидент|watch_brief|дежур|пайплайн|цепочк|ночной бриф|saveToFile|summarize|"
    r"разбор смены|orchestration|несколько сервер"
)


def _extract_json_blob(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return ""


def _next_pipeline_call(last: str, names: set[str]) -> tuple[str, dict[str, object]] | None:
    blob = _extract_json_blob(last)
    if "Результат MCP search" in last and "summarize" in names:
        return "summarize", {"payload": blob}
    if "Результат MCP summarize" in last and "saveToFile" in names:
        return "saveToFile", {"brief": blob, "name": "night-brief"}
    return None


def _openai_tool_names(tools: list[dict[str, object]] | None) -> set[str]:
    names: set[str] = set()
    for item in tools or []:
        fn = item.get("function") if isinstance(item, dict) else None
        if isinstance(fn, dict) and fn.get("name"):
            names.add(str(fn["name"]))
        elif isinstance(item, dict) and item.get("name"):
            names.add(str(item["name"]))
    return names


def _summarize_mcp_followup(last: str) -> str:
    start = last.find("{")
    end = last.rfind("}")
    blob: dict[str, object] = {}
    if start >= 0 and end > start:
        try:
            parsed = json.loads(last[start : end + 1])
            if isinstance(parsed, dict):
                blob = parsed
        except json.JSONDecodeError:
            blob = {}
    payload = blob.get("payload")
    healthy = blob.get("ok") is True or (
        isinstance(payload, dict) and payload.get("status") == "ok"
    )
    if healthy:
        return (
            f"Стенд отвечает. /health = ok, задержка {blob.get('latency_ms', '—')} мс. "
            "Можно работать дальше."
        )
    if blob.get("source") == "saveToFile" or blob.get("path"):
        return f"Бриф сохранён: {blob.get('path') or blob.get('title')}"
    if blob.get("source") == "summarize" and blob.get("body"):
        return str(blob.get("body"))
    if blob.get("severity") and blob.get("open_incidents") is not None:
        return f"Вахта {blob.get('severity')}: {blob.get('summary')}"
    if blob.get("summary"):
        return f"Последняя сводка: {blob['summary']}"
    if blob.get("first_digest") or blob.get("job_id"):
        digest = blob.get("first_digest") if isinstance(blob.get("first_digest"), dict) else {}
        summary = digest.get("summary") if isinstance(digest, dict) else ""
        interval = blob.get("interval_seconds")
        return f"Периодическая сводка поставлена ({interval} с). {summary}".strip()
    if blob.get("ranking") is not None:
        ranking = blob.get("ranking") or []
        top = ranking[0] if isinstance(ranking, list) and ranking else None
        hours = blob.get("hours", 24)
        if isinstance(top, dict) and top.get("model_id"):
            return f"Рейтинг за {hours} ч: лидер {top.get('model_id')} (score {top.get('score')})."
        count = len(ranking) if isinstance(ranking, list) else 0
        return f"Рейтинг за {hours} ч получен. Моделей в выборке: {count}."
    if "Результат MCP" in last:
        return "Инструмент вернул данные. Смотри JSON в трассировке вызова."
    return DEMO_ANSWER


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
        last = next((m.content for m in reversed(messages) if m.content), "")
        names = _openai_tool_names(tools) if tools else set()
        if "Результат MCP" in last:
            nxt = _next_pipeline_call(last, names)
            if nxt is not None:
                pipe_name, pipe_args = nxt
                return CompletionResult(
                    content="",
                    model_id=self._resolve(model),
                    tool_calls=[
                        ToolCallRequest(id="fake-pipe", name=pipe_name, arguments=pipe_args)
                    ],
                )
            return CompletionResult(
                content=_summarize_mcp_followup(last),
                model_id=self._resolve(model),
            )
        if tools:
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
            if _PULSE_HINT.search(last) and names:
                name = "probe_stand"
                arguments: dict[str, object] = {}
                if re.search(r"(?i)разбор смены|orchestration|несколько сервер", last) and (
                    "watch_brief" in names
                ):
                    name = "watch_brief"
                elif (
                    re.search(r"(?i)пайплайн|цепочк|ночной бриф|saveToFile|архив бриф", last)
                    and "search" in names
                ):
                    name = "search"
                    arguments = {"hours": 24}
                elif (
                    re.search(r"(?i)вахт|инцидент|watch_brief|дежур", last)
                    and "watch_brief" in names
                ):
                    name = "watch_brief"
                elif (
                    re.search(r"(?i)расписан|schedule|каждые", last) and "schedule_digest" in names
                ):
                    name = "schedule_digest"
                    arguments = {"interval_seconds": 60, "hours": 24, "note": "pulse"}
                elif (
                    re.search(r"(?i)рейтинг|ranking|pareto|model_pulse", last)
                    and "model_pulse" in names
                ):
                    name = "model_pulse"
                    arguments = {"hours": 24}
                elif (
                    re.search(r"(?i)сводк|digest|latest_digest", last) and "latest_digest" in names
                ):
                    name = "latest_digest"
                elif "probe_stand" not in names:
                    name = next(iter(names))
                if name in names:
                    return CompletionResult(
                        content="",
                        model_id=self._resolve(model),
                        tool_calls=[
                            ToolCallRequest(id="fake-pulse-1", name=name, arguments=arguments)
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

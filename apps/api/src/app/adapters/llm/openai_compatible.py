"""OpenAI-compatible chat provider (OpenRouter, DeepSeek, …).

Switching provider is a matter of ``LLM_BASE_URL`` + ``LLM_API_KEY``; no new
domain types. Nothing here logs the payload, the key, or the response body.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.domain.entities import ChatMessage, CompletionResult, TokenChunk
from app.domain.errors import LLMProviderError
from app.domain.generation import GenerationParams
from app.domain.media import parse_openai_tool_calls

logger = logging.getLogger(__name__)

_DONE = "[DONE]"
_DATA_PREFIX = "data:"
_STREAM_END = object()
#: The chunk carried only chain-of-thought, no answer text.
_REASONING_ONLY = object()

#: Reasoning models put their thinking here instead of in ``content``.
#: OpenRouter uses ``reasoning``, DeepSeek ``reasoning_content``.
_REASONING_KEYS = ("reasoning", "reasoning_content")
DEFAULT_TIMEOUT_SECONDS = 60.0


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        proxy: str | None = None,
        client: httpx.AsyncClient | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._extra_headers = {k: v for k, v in (extra_headers or {}).items() if v}
        proxy_url = proxy.strip() if proxy else None
        self._client = (
            client
            if client is not None
            else httpx.AsyncClient(timeout=timeout, proxy=proxy_url or None)
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @property
    def _url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self._extra_headers}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    @staticmethod
    def _payload(
        messages: list[ChatMessage],
        model: str,
        *,
        stream: bool,
        generation: GenerationParams | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "stream": stream,
            "messages": [{"role": str(m.role), "content": m.content} for m in messages],
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if generation is None:
            return body
        if generation.temperature is not None:
            body["temperature"] = generation.temperature
        max_tokens = generation.resolved_max_tokens()
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if generation.stop:
            body["stop"] = list(generation.stop)
        # DeepSeek V3.2 / V4 (and some OpenRouter mirrors) enable thinking by
        # default. In thinking mode temperature / top_p are accepted but ignored.
        # Always send an explicit on/off so sampling knobs actually apply when
        # the UI asks for non-reasoning answers.
        if generation.reasoning:
            body["reasoning"] = {"enabled": True}
        else:
            body["reasoning"] = {"enabled": False}
            body["thinking"] = {"type": "disabled"}
        return body

    @staticmethod
    def _empty_error(model: str) -> LLMProviderError:
        """No answer text at all — usually a reasoning model cut off mid-thought.

        Marked retryable so the router moves on to the next model. That does not
        break the "no failover after the first token" rule: reasoning is never
        forwarded downstream, so the reader has seen nothing yet.
        """
        return LLMProviderError(
            "Provider streamed no answer content.", kind="empty", model_id=model
        )

    @staticmethod
    def _http_error(status: int, model: str) -> LLMProviderError:
        # The body may echo the prompt or the key — it never reaches the message.
        return LLMProviderError(f"Provider returned HTTP {status}.", status=status, model_id=model)

    @staticmethod
    def _transport_error(exc: Exception, model: str) -> LLMProviderError:
        kind = "timeout" if isinstance(exc, httpx.TimeoutException) else "transport"
        return LLMProviderError(f"Provider request failed ({kind}).", kind=kind, model_id=model)

    @staticmethod
    def _resolved_model(body: dict[str, Any], requested: str) -> str:
        """Prefer what the provider says it used — it may have rerouted us."""
        reported = body.get("model")
        return str(reported) if reported else requested

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> CompletionResult:
        try:
            response = await self._client.post(
                self._url,
                json=self._payload(
                    messages, model, stream=False, generation=generation, tools=tools
                ),
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise self._transport_error(exc, model) from exc

        if response.status_code >= 400:
            raise self._http_error(response.status_code, model)

        try:
            body: dict[str, Any] = response.json()
            message = body["choices"][0]["message"]
            content = message.get("content") or ""
            tool_calls = parse_openai_tool_calls(message) if tools else []
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                "Provider returned an unreadable response.", kind="malformed", model_id=model
            ) from exc

        if not str(content).strip() and not tool_calls:
            raise self._empty_error(model)

        return CompletionResult(
            content=str(content),
            model_id=self._resolved_model(body, model),
            tool_calls=tool_calls or None,
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None = None,
    ) -> AsyncIterator[TokenChunk]:
        payload = self._payload(messages, model, stream=True, generation=generation)
        emitted = False
        reasoning_seen = False
        try:
            async with self._client.stream(
                "POST", self._url, json=payload, headers=self._headers()
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise self._http_error(response.status_code, model)

                async for line in response.aiter_lines():
                    parsed = self._parse_line(line, model)
                    if parsed is _STREAM_END:
                        break
                    if parsed is _REASONING_ONLY:
                        reasoning_seen = True
                        continue
                    if isinstance(parsed, TokenChunk):
                        emitted = True
                        yield parsed
        except httpx.HTTPError as exc:
            raise self._transport_error(exc, model) from exc

        if not emitted:
            if reasoning_seen:
                logger.info("model produced only reasoning model_id=%s", model)
            raise self._empty_error(model)

    def _parse_line(self, line: str, model: str) -> TokenChunk | object | None:
        """Return a chunk, ``_STREAM_END``, or ``None`` for lines to skip."""
        line = line.strip()
        if not line or not line.startswith(_DATA_PREFIX):
            return None
        data = line[len(_DATA_PREFIX) :].strip()
        if data == _DONE:
            return _STREAM_END
        try:
            body: dict[str, Any] = json.loads(data)
            chunk = body["choices"][0]["delta"]
            delta = chunk.get("content")
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError):
            # Keep-alives and vendor-specific frames are not an error.
            return None
        if not delta:
            # Thinking is not an answer, so it is never forwarded — but it does
            # tell us the model was alive, which changes how we report failure.
            if any(chunk.get(key) for key in _REASONING_KEYS):
                return _REASONING_ONLY
            return None
        return TokenChunk(text=str(delta), model_id=self._resolved_model(body, model))

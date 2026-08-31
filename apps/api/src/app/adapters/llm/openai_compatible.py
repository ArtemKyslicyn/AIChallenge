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

logger = logging.getLogger(__name__)

_DONE = "[DONE]"
_DATA_PREFIX = "data:"
_STREAM_END = object()
DEFAULT_TIMEOUT_SECONDS = 60.0


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client if client is not None else httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @property
    def _url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    @staticmethod
    def _payload(messages: list[ChatMessage], model: str, *, stream: bool) -> dict[str, Any]:
        return {
            "model": model,
            "stream": stream,
            "messages": [{"role": str(m.role), "content": m.content} for m in messages],
        }

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

    async def complete_chat(self, messages: list[ChatMessage], model: str) -> CompletionResult:
        try:
            response = await self._client.post(
                self._url,
                json=self._payload(messages, model, stream=False),
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise self._transport_error(exc, model) from exc

        if response.status_code >= 400:
            raise self._http_error(response.status_code, model)

        try:
            body: dict[str, Any] = response.json()
            content = body["choices"][0]["message"]["content"] or ""
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                "Provider returned an unreadable response.", kind="malformed", model_id=model
            ) from exc

        return CompletionResult(content=str(content), model_id=self._resolved_model(body, model))

    async def stream_chat(
        self, messages: list[ChatMessage], model: str
    ) -> AsyncIterator[TokenChunk]:
        payload = self._payload(messages, model, stream=True)
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
                        return
                    if isinstance(parsed, TokenChunk):
                        yield parsed
        except httpx.HTTPError as exc:
            raise self._transport_error(exc, model) from exc

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
            delta = body["choices"][0]["delta"].get("content")
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError):
            # Keep-alives and vendor-specific frames are not an error.
            return None
        if not delta:
            return None
        return TokenChunk(text=str(delta), model_id=self._resolved_model(body, model))

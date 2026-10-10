"""Native Ollama /api/chat. The OpenAI shim leaves qwen content empty."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.domain.entities import ChatMessage, CompletionResult, TokenChunk
from app.domain.errors import LLMProviderError
from app.domain.generation import GenerationParams
from app.domain.local_llm import canonical_model_id, upstream_model_id

_TAGS_TIMEOUT = 8.0
_CHAT_TIMEOUT = 120.0
TAGS_ERROR = "Ollama не ответил на /api/tags"
UNREACHABLE = "Ollama недоступен по этому адресу."


class OllamaNativeProvider:
    def __init__(
        self,
        origin: str,
        api_key: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._origin = origin.rstrip("/")
        self._api_key = (api_key or "").strip() or None
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {"Authorization": f"Bearer {self._api_key}"}

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=timeout)

    def _resolved(self, model: str) -> tuple[str, str]:
        upstream = upstream_model_id(model) or model
        return upstream, canonical_model_id(upstream)

    def _body(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None,
        stream: bool,
    ) -> dict[str, Any]:
        upstream, _canonical = self._resolved(model)
        body: dict[str, Any] = {
            "model": upstream,
            "messages": [
                {"role": message.role.value, "content": message.content} for message in messages
            ],
            "stream": stream,
            "think": bool(generation.reasoning) if generation is not None else False,
        }
        options: dict[str, Any] = {}
        if generation is not None:
            if generation.temperature is not None:
                options["temperature"] = generation.temperature
            max_tokens = generation.resolved_max_tokens()
            if max_tokens is not None:
                options["num_predict"] = max_tokens
            if generation.stop:
                options["stop"] = list(generation.stop)
        if options:
            body["options"] = options
        return body

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> CompletionResult:
        del tools
        _upstream, canonical = self._resolved(model)
        payload = self._body(messages, model, generation=generation, stream=False)
        try:
            async with self._client(_CHAT_TIMEOUT) as client:
                response = await client.post(
                    f"{self._origin}/api/chat",
                    json=payload,
                    headers=self._headers(),
                )
        except httpx.TimeoutException as exc:
            raise LLMProviderError(UNREACHABLE, kind="timeout", model_id=canonical) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(UNREACHABLE, kind="transport", model_id=canonical) from exc
        if response.status_code >= 400:
            raise LLMProviderError(
                UNREACHABLE,
                status=response.status_code,
                kind="transport",
                model_id=canonical,
            )
        data = response.json()
        message = data.get("message") if isinstance(data, dict) else None
        text = ""
        if isinstance(message, dict):
            text = str(message.get("content") or "")
        if not text.strip():
            raise LLMProviderError(
                "Ollama вернул пустой ответ.",
                kind="empty",
                model_id=canonical,
            )
        return CompletionResult(content=text, model_id=canonical)

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None = None,
    ) -> AsyncIterator[TokenChunk]:
        _upstream, canonical = self._resolved(model)
        payload = self._body(messages, model, generation=generation, stream=True)
        emitted = False
        try:
            async with self._client(_CHAT_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    f"{self._origin}/api/chat",
                    json=payload,
                    headers=self._headers(),
                ) as response:
                    if response.status_code >= 400:
                        raise LLMProviderError(
                            UNREACHABLE,
                            status=response.status_code,
                            kind="transport",
                            model_id=canonical,
                        )
                    async for line in response.aiter_lines():
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            data = json.loads(stripped)
                        except json.JSONDecodeError as exc:
                            raise LLMProviderError(
                                UNREACHABLE,
                                kind="transport",
                                model_id=canonical,
                            ) from exc
                        message = data.get("message") if isinstance(data, dict) else None
                        text = ""
                        if isinstance(message, dict):
                            text = str(message.get("content") or "")
                        if not text:
                            continue
                        emitted = True
                        yield TokenChunk(text=text, model_id=canonical)
        except LLMProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise LLMProviderError(UNREACHABLE, kind="timeout", model_id=canonical) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(UNREACHABLE, kind="transport", model_id=canonical) from exc
        if not emitted:
            raise LLMProviderError(
                "Ollama вернул пустой ответ.",
                kind="empty",
                model_id=canonical,
            )


async def fetch_ollama_tags(
    origin: str,
    api_key: str | None,
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[str, ...]:
    owns = client is None
    http = client or httpx.AsyncClient(timeout=_TAGS_TIMEOUT)
    headers = {"Authorization": f"Bearer {api_key}"} if (api_key or "").strip() else {}
    try:
        response = await http.get(f"{origin.rstrip('/')}/api/tags", headers=headers)
    except httpx.TimeoutException as exc:
        raise LLMProviderError(UNREACHABLE, kind="timeout") from exc
    except httpx.HTTPError as exc:
        raise LLMProviderError(UNREACHABLE, kind="transport") from exc
    finally:
        if owns:
            await http.aclose()
    if response.status_code != 200:
        raise LLMProviderError(TAGS_ERROR, kind="transport", status=response.status_code)
    payload = response.json()
    rows = payload.get("models") if isinstance(payload, dict) else None
    names: list[str] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            names.append(name)
    return tuple(names)

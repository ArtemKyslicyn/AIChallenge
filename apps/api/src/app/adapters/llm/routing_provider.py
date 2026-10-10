"""Send ollama/ pins to native chat and leave every other id on the cloud provider."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from app.adapters.llm.ollama_native import OllamaNativeProvider
from app.domain.entities import ChatMessage, CompletionResult, TokenChunk
from app.domain.errors import LLMProviderError
from app.domain.generation import GenerationParams
from app.domain.local_llm import current_local_llm_source, upstream_model_id
from app.domain.ports import LLMProvider

_CONNECT_HINT = "Подключите локальную модель в Профиле."


class RoutingLLMProvider:
    def __init__(
        self,
        cloud: LLMProvider,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._cloud = cloud
        self._transport = transport

    async def aclose(self) -> None:
        close = getattr(self._cloud, "aclose", None)
        if close is not None:
            await close()

    def _local(self, model: str) -> OllamaNativeProvider:
        upstream = upstream_model_id(model)
        source = current_local_llm_source()
        if (
            upstream is None
            or source is None
            or not source.enabled
            or upstream not in source.models
        ):
            raise LLMProviderError(_CONNECT_HINT, kind="config", model_id=model)
        return OllamaNativeProvider(source.base_url, source.api_key, transport=self._transport)

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> CompletionResult:
        if upstream_model_id(model) is not None:
            return await self._local(model).complete_chat(
                messages, model, generation=generation, tools=tools
            )
        return await self._cloud.complete_chat(messages, model, generation=generation, tools=tools)

    def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None = None,
    ) -> AsyncIterator[TokenChunk]:
        if upstream_model_id(model) is not None:
            return self._local(model).stream_chat(messages, model, generation=generation)
        return self._cloud.stream_chat(messages, model, generation=generation)

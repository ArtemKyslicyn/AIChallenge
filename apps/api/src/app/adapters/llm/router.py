"""Ordered model chain with failover.

The one rule that shapes everything here: a stream may only fail over
*before* its first token. Once the client has seen text from one model,
switching to another would splice two different completions together.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence

from app.domain.entities import ChatMessage, CompletionResult, TokenChunk
from app.domain.errors import LLMExhaustedError, LLMProviderError, LLMStreamAbortedError
from app.domain.ports import LLMProvider

logger = logging.getLogger(__name__)

AUTO = "auto"

#: Upstream statuses that mean "this model is unavailable right now", not
#: "this request is wrong": rate limit, out of credit, upstream timeout.
RETRYABLE_STATUSES = frozenset({402, 408, 429})
RETRYABLE_KINDS = frozenset({"quota", "rate_limit", "timeout"})

DEFAULT_EXHAUSTED_TTL_SECONDS = 300


def _is_retryable(exc: LLMProviderError) -> bool:
    return exc.status in RETRYABLE_STATUSES or exc.kind in RETRYABLE_KINDS


class ModelRouter:
    """Picks a model from the chain and reports which one actually answered.

    Exhaustion state is per-process in v1; a Redis-backed store can replace it
    later without changing this class's surface.
    """

    def __init__(
        self,
        provider: LLMProvider,
        model_chain: Sequence[str],
        exhausted_ttl_seconds: int = DEFAULT_EXHAUSTED_TTL_SECONDS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._provider = provider
        self._chain = list(model_chain)
        self._ttl = exhausted_ttl_seconds
        self._now = now
        self._exhausted: dict[str, float] = {}

    def _mark_exhausted(self, model: str) -> None:
        self._exhausted[model] = self._now() + self._ttl
        logger.warning("model exhausted model_id=%s ttl_seconds=%s", model, self._ttl)

    def _candidates(self, preferred_model: str = AUTO) -> list[str]:
        """Chain order, with an explicit ``preferred_model`` pinned first.

        A pinned model that is exhausted or absent from the chain simply loses
        its priority — it does not disable the rest of the chain.
        """
        ordered: list[str] = []
        if preferred_model and preferred_model != AUTO:
            ordered.append(preferred_model)
        ordered.extend(model for model in self._chain if model not in ordered)

        now = self._now()
        available: list[str] = []
        for model in ordered:
            until = self._exhausted.get(model)
            if until is not None:
                if now < until:
                    continue
                del self._exhausted[model]
            available.append(model)
        return available

    async def complete_chat(
        self, messages: list[ChatMessage], preferred_model: str = AUTO
    ) -> CompletionResult:
        candidates = self._candidates(preferred_model)
        if not candidates:
            raise LLMExhaustedError("No model is currently available.")

        last_error: LLMProviderError | None = None
        for model in candidates:
            try:
                return await self._provider.complete_chat(messages, model)
            except LLMProviderError as exc:
                if not _is_retryable(exc):
                    raise
                self._mark_exhausted(model)
                last_error = exc
        raise LLMExhaustedError("No model in the chain could serve the request.") from last_error

    async def stream_chat(
        self, messages: list[ChatMessage], preferred_model: str = AUTO
    ) -> AsyncIterator[TokenChunk]:
        candidates = self._candidates(preferred_model)
        if not candidates:
            raise LLMExhaustedError("No model is currently available.")

        last_error: LLMProviderError | None = None
        for model in candidates:
            emitted: list[str] = []
            try:
                async for chunk in self._provider.stream_chat(messages, model):
                    emitted.append(chunk.text)
                    yield chunk
            except LLMProviderError as exc:
                if emitted:
                    # Past the point of no return: hand the partial answer back
                    # so the caller can persist it, and stop.
                    raise LLMStreamAbortedError(
                        model_id=model, partial_text="".join(emitted)
                    ) from exc
                if not _is_retryable(exc):
                    raise
                self._mark_exhausted(model)
                last_error = exc
                continue
            return
        raise LLMExhaustedError("No model in the chain could serve the request.") from last_error

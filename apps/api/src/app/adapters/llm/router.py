"""Ordered model chain with failover.

The one rule that shapes everything here: a stream may only fail over
*before* its first token. Once the client has seen text from one model,
switching to another would splice two different completions together.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence

from app.domain.entities import AUTO_MODEL, ChatMessage, CompletionResult, TokenChunk
from app.domain.errors import LLMExhaustedError, LLMProviderError, LLMStreamAbortedError
from app.domain.generation import GenerationParams
from app.domain.ports import LLMProvider

logger = logging.getLogger(__name__)

#: Upstream statuses that mean "this model is unavailable right now", not
#: "this request is wrong": rate limit, out of credit, upstream timeout,
#: region block, temporary outage, missing/retired free model id (404),
#: and common gateway blips (5xx).
#:
#: 401 is deliberately absent. A rejected credential will not become valid on
#: the next model, so retrying only burns the whole chain, marks every model
#: exhausted for the TTL, and turns a plain authentication failure into
#: "no model is available" — which sends whoever debugs it the wrong way.
RETRYABLE_STATUSES = frozenset({402, 403, 404, 408, 429, 500, 502, 503, 504})

#: A rejected credential disqualifies a whole *tier*, not one model: every model
#: in a chain shares one key. So 401 is fatal inside a chain (above) but is a
#: reason for TieredModelRouter to try the next provider, which has its own key.
TIER_FATAL_STATUSES = frozenset({401})
#: "empty" is retryable on purpose: a model that streams only chain-of-thought
#: and no answer has shown the reader nothing, so moving on is still safe.
#: "transport" covers proxy/connect blips before any token is shown.
RETRYABLE_KINDS = frozenset({"quota", "rate_limit", "timeout", "empty", "transport"})

DEFAULT_EXHAUSTED_TTL_SECONDS = 300

#: How many models one request may try before giving up. Without a cap a long
#: free chain turns a single message into minutes of silent retrying.
DEFAULT_MAX_ATTEMPTS = 5

#: How long to wait for a model to produce its *first* answer token. Reasoning
#: models can think for a long time and then run out of budget without writing
#: anything; that must cost one bounded wait, not the whole request.
DEFAULT_FIRST_TOKEN_TIMEOUT_SECONDS = 25.0


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
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        first_token_timeout_seconds: float = DEFAULT_FIRST_TOKEN_TIMEOUT_SECONDS,
    ) -> None:
        self._provider = provider
        self._chain = list(model_chain)
        self._ttl = exhausted_ttl_seconds
        self._now = now
        self._max_attempts = max(1, max_attempts)
        self._first_token_timeout = first_token_timeout_seconds
        self._exhausted: dict[str, float] = {}

    def _mark_exhausted(self, model: str, *, reason: str = "") -> None:
        self._exhausted[model] = self._now() + self._ttl
        if reason:
            logger.warning(
                "model exhausted model_id=%s ttl_seconds=%s reason=%s",
                model,
                self._ttl,
                reason,
            )
        else:
            logger.warning("model exhausted model_id=%s ttl_seconds=%s", model, self._ttl)

    @staticmethod
    def _fail_reason(exc: LLMProviderError) -> str:
        if exc.status is not None:
            return f"http_{exc.status}"
        return exc.kind or "unknown"

    def _candidates(self, preferred_model: str = AUTO_MODEL) -> list[str]:
        """Chain order, with an explicit ``preferred_model`` pinned first.

        A pinned model that is exhausted or absent from the chain simply loses
        its priority — it does not disable the rest of the chain.
        """
        ordered: list[str] = []
        if preferred_model and preferred_model != AUTO_MODEL:
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
        # One request walks a bounded prefix of the chain, not all of it.
        return available[: self._max_attempts]

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = AUTO_MODEL,
        *,
        generation: GenerationParams | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> CompletionResult:
        candidates = self._candidates(preferred_model)
        if not candidates:
            raise LLMExhaustedError("Сейчас нет доступной модели.")

        last_error: LLMProviderError | None = None
        for model in candidates:
            try:
                return await self._provider.complete_chat(
                    messages, model, generation=generation, tools=tools
                )
            except LLMProviderError as exc:
                if not _is_retryable(exc):
                    raise
                self._mark_exhausted(model, reason=self._fail_reason(exc))
                last_error = exc
        raise LLMExhaustedError("Ни одна модель из цепочки не смогла ответить.") from last_error

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = AUTO_MODEL,
        *,
        generation: GenerationParams | None = None,
    ) -> AsyncIterator[TokenChunk]:
        candidates = self._candidates(preferred_model)
        if not candidates:
            raise LLMExhaustedError("Сейчас нет доступной модели.")

        last_error: LLMProviderError | None = None
        for model in candidates:
            emitted: list[str] = []
            stream = self._provider.stream_chat(messages, model, generation=generation)
            try:
                while True:
                    # Only the wait for the first token is bounded. After that
                    # the model is clearly answering and must not be cut off.
                    budget = self._first_token_timeout if not emitted else None
                    try:
                        chunk = await asyncio.wait_for(anext(stream), budget)
                    except StopAsyncIteration:
                        break
                    except TimeoutError as exc:
                        raise LLMProviderError(
                            "Provider did not start answering in time.",
                            kind="timeout",
                            model_id=model,
                        ) from exc
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
                self._mark_exhausted(model, reason=self._fail_reason(exc))
                last_error = exc
                continue
            finally:
                # The port promises only an AsyncIterator, so closing is
                # best-effort — but an async generator must be closed, or the
                # provider's HTTP stream is left dangling.
                close = getattr(stream, "aclose", None)
                if close is not None:
                    await close()
            return
        raise LLMExhaustedError("Ни одна модель из цепочки не смогла ответить.") from last_error


class TieredModelRouter:
    """Run model chains on multiple providers in order.

    The next tier is tried only when every model in the current tier is
    exhausted (429/quota/timeout). Mid-stream aborts are never retried on
    another tier — same rule as :class:`ModelRouter`.
    """

    def __init__(self, tiers: Sequence[ModelRouter]) -> None:
        if not tiers:
            raise ValueError("at least one ModelRouter tier is required")
        self._tiers = list(tiers)

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = AUTO_MODEL,
        *,
        generation: GenerationParams | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> CompletionResult:
        last_error: Exception | None = None
        for index, tier in enumerate(self._tiers):
            try:
                return await tier.complete_chat(
                    messages, preferred_model, generation=generation, tools=tools
                )
            except LLMExhaustedError as exc:
                logger.warning("llm tier exhausted tier_index=%s", index)
                last_error = exc
            except LLMProviderError as exc:
                if exc.status not in TIER_FATAL_STATUSES:
                    raise
                logger.warning("llm tier rejected the credential tier_index=%s", index)
                last_error = exc
        raise LLMExhaustedError("Ни одна модель из цепочки не смогла ответить.") from last_error

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = AUTO_MODEL,
        *,
        generation: GenerationParams | None = None,
    ) -> AsyncIterator[TokenChunk]:
        last_error: Exception | None = None
        for index, tier in enumerate(self._tiers):
            emitted = False
            try:
                async for chunk in tier.stream_chat(
                    messages, preferred_model, generation=generation
                ):
                    emitted = True
                    yield chunk
                return
            except LLMExhaustedError as exc:
                # Same rule as inside a chain: once the reader has seen text,
                # no other tier may continue the answer.
                if emitted:
                    raise
                logger.warning("llm tier exhausted tier_index=%s", index)
                last_error = exc
            except LLMProviderError as exc:
                if emitted or exc.status not in TIER_FATAL_STATUSES:
                    raise
                logger.warning("llm tier rejected the credential tier_index=%s", index)
                last_error = exc
        raise LLMExhaustedError("Ни одна модель из цепочки не смогла ответить.") from last_error

"""Try a cheap model first, and decide *before* the reader sees anything.

The cascade is deliberately allowed to fail: every unexpected outcome — a
provider error, a timeout, a question too long to be worth the gamble — returns
``CASCADE_OFF`` and lets the normal streaming path run untouched. A cost
optimisation must never be able to cost someone their answer.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.domain.cascade import CASCADE_CHEAP, CASCADE_ESCALATED, CASCADE_OFF, AnswerScorer
from app.domain.entities import ChatMessage, MessageRole
from app.domain.errors import LLMExhaustedError, LLMProviderError
from app.domain.ports import ChatRouter
from app.domain.tracing import AttemptRecord

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CascadeOutcome:
    """What the cheap stage decided, in the vocabulary the trace speaks.

    ``accepted_text`` is the only field that changes what the reader sees; the
    rest is the record of how the decision was reached.
    """

    accepted_text: str | None
    model_id: str | None
    stage: str
    cheap_model_id: str | None = None
    cheap_score: float | None = None


def _off() -> CascadeOutcome:
    return CascadeOutcome(accepted_text=None, model_id=None, stage=CASCADE_OFF)


def _last_question(turns: list[ChatMessage]) -> str:
    for turn in reversed(turns):
        if turn.role is MessageRole.USER:
            return turn.content
    return ""


async def try_cheap_first(
    *,
    turns: list[ChatMessage],
    router: ChatRouter,
    scorer: AnswerScorer,
    cheap_models: list[str],
    attempts: list[AttemptRecord],
    timeout_seconds: float,
    max_question_chars: int,
) -> CascadeOutcome:
    question = _last_question(turns)
    if not cheap_models or len(question) > max_question_chars:
        return _off()

    cheap_model = cheap_models[0]
    try:
        async with asyncio.timeout(timeout_seconds):
            result = await router.complete_chat(turns, cheap_model, attempts=attempts)
    except (TimeoutError, LLMExhaustedError, LLMProviderError) as exc:
        # Дешёвый этап — ставка. Проигранная ставка стоит задержки, но не ответа.
        logger.info("cascade cheap stage skipped model_id=%s reason=%s", cheap_model, exc)
        return _off()

    verdict = scorer.score(question, result.content)
    if verdict.accepted:
        return CascadeOutcome(
            accepted_text=result.content,
            model_id=result.model_id,
            stage=CASCADE_CHEAP,
            cheap_model_id=result.model_id,
            cheap_score=verdict.score,
        )

    logger.info(
        "cascade escalating model_id=%s score=%.2f reason=%s",
        result.model_id,
        verdict.score,
        verdict.reason,
    )
    return CascadeOutcome(
        accepted_text=None,
        model_id=None,
        stage=CASCADE_ESCALATED,
        cheap_model_id=result.model_id,
        cheap_score=verdict.score,
    )

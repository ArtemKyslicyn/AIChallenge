"""An answer judge built on the model chain, plus the budget that bounds it.

Two rules shape the whole file:

* the judge never raises — it is measuring the chat, and a measurement that
  can break what it measures is worse than no measurement at all;
* the judge never scores its own text — models systematically prefer their own
  writing, and a self-graded column is a column of self-regard.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable

from app.adapters.lab.rubric import JudgeRubric
from app.application.quality import parse_verdict
from app.domain.entities import ChatMessage, MessageRole
from app.domain.errors import LLMExhaustedError, LLMProviderError
from app.domain.ports import ChatRouter
from app.domain.quality import QualityVerdict

logger = logging.getLogger(__name__)

HOUR_SECONDS = 3600.0


class HourlyJudgeBudget:
    """How many judgements this process has spent in the last hour.

    In-process like :class:`~app.adapters.llm.feedback_penalties.FeedbackPenaltyCache`,
    and for the same reason: the caller asks on the path of a request, so the
    answer has to already be in memory. A sliding window rather than a
    tumbling one, so a traffic spike cannot spend two hours of budget across
    one clock boundary.
    """

    def __init__(self, *, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        # Bounded in practice: the caller stops taking once the cap is hit.
        self._spent: deque[float] = deque()

    def _prune(self) -> None:
        cutoff = self._now() - HOUR_SECONDS
        while self._spent and self._spent[0] <= cutoff:
            self._spent.popleft()

    def used(self) -> int:
        self._prune()
        return len(self._spent)

    def take(self) -> None:
        """Count one outbound judge call, spent or wasted.

        Counted at the decision, not at the verdict: the cap exists to bound
        what the judge costs, and a call that failed cost the same as one that
        parsed.
        """
        self._prune()
        self._spent.append(self._now())


class LLMAnswerJudge:
    """Scores one answer through the chain, and gives up quietly on anything else."""

    def __init__(
        self,
        *,
        router: ChatRouter,
        model_id: str,
        rubric: JudgeRubric,
        timeout_seconds: float,
    ) -> None:
        self._router = router
        self._model_id = model_id
        self._rubric = rubric
        self._timeout = timeout_seconds

    async def judge(self, question: str, answer: str, *, answered_by: str) -> QualityVerdict | None:
        if not self._model_id:
            return None
        if answered_by and answered_by == self._model_id:
            logger.info("judge skipped self-evaluation model_id=%s", answered_by)
            return None

        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=self._rubric.system),
            ChatMessage(role=MessageRole.USER, content=self._rubric.render(question, answer)),
        ]
        try:
            async with asyncio.timeout(self._timeout):
                result = await self._router.complete_chat(messages, self._model_id)
        except (TimeoutError, LLMExhaustedError, LLMProviderError) as exc:
            logger.info("judge call failed model_id=%s reason=%s", self._model_id, exc)
            return None
        except Exception:
            # The chain can fail in ways this adapter has not imagined. None of
            # them are allowed to reach the caller, which is finishing a chat.
            logger.warning("judge call raised model_id=%s", self._model_id, exc_info=True)
            return None

        # The pin is a preference, not a guarantee: an exhausted judge model
        # sends the request down the same chain that wrote the answer.
        if result.model_id == answered_by:
            logger.info("judge skipped self-evaluation after failover model_id=%s", answered_by)
            return None
        return parse_verdict(result.content, judge_model_id=result.model_id)

"""Hourly cap for pinned ollama/ calls, counted per signed-in user."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from app.domain.errors import LocalLlmRateLimitError
from app.domain.local_llm import LOCAL_LLM_PREFIX

RATE_LIMIT_MESSAGE = "Слишком много запросов подряд. Подождите немного и напишите снова."


class LocalLlmRateLimiter:
    def __init__(self, *, limit_per_hour: int) -> None:
        self._limit = max(0, int(limit_per_hour))
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check_and_record(self, user_id: str) -> None:
        if self._limit <= 0:
            return
        key = (user_id or "").strip()
        if not key:
            return
        now = time.monotonic()
        cutoff = now - 3600.0
        stamps = [stamp for stamp in self._hits[key] if stamp >= cutoff]
        if len(stamps) >= self._limit:
            self._hits[key] = stamps
            raise LocalLlmRateLimitError(RATE_LIMIT_MESSAGE)
        stamps.append(now)
        self._hits[key] = stamps


def charge_local_pin(
    limiter: LocalLlmRateLimiter,
    *,
    user_id: UUID | None,
    models: Sequence[str],
) -> None:
    if user_id is None:
        return
    if any(model.startswith(LOCAL_LLM_PREFIX) for model in models):
        limiter.check_and_record(str(user_id))

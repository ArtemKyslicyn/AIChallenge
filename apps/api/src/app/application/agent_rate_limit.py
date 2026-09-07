"""In-process hourly cap for agent-workshop runs (per visitor id)."""

from __future__ import annotations

import time
from collections import defaultdict

from app.domain.errors import AgentRunRateLimitError


class AgentRunRateLimiter:
    def __init__(self, *, limit_per_hour: int) -> None:
        self._limit = max(0, int(limit_per_hour))
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check_and_record(self, visitor_key: str) -> None:
        if self._limit <= 0:
            return
        key = (visitor_key or "anonymous").strip() or "anonymous"
        now = time.monotonic()
        cutoff = now - 3600.0
        stamps = [t for t in self._hits[key] if t >= cutoff]
        if len(stamps) >= self._limit:
            self._hits[key] = stamps
            raise AgentRunRateLimitError(
                f"Лимит запусков агента: не больше {self._limit} в час."
            )
        stamps.append(now)
        self._hits[key] = stamps

"""Outbound product analytics (fail-open)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(slots=True, frozen=True)
class AnalyticsEvent:
    name: str
    distinct_id: str
    properties: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime | None = None


class AnalyticsCapture(Protocol):
    """Fire-and-forget product events. Implementations must not raise to callers."""

    async def capture(self, events: list[AnalyticsEvent]) -> None: ...

    async def aclose(self) -> None: ...

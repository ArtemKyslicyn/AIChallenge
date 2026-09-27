"""Fail-open analytics for guest MCP funnel events."""

from __future__ import annotations

import logging
from typing import Any

from app.domain.analytics import AnalyticsCapture, AnalyticsEvent

logger = logging.getLogger(__name__)


async def emit_guest_event(
    analytics: AnalyticsCapture,
    name: str,
    distinct_id: str,
    props: dict[str, Any],
) -> None:
    try:
        await analytics.capture(
            [AnalyticsEvent(name=name, distinct_id=distinct_id, properties=props)]
        )
    except Exception:
        logger.exception("guest_mcp analytics emit failed event=%s", name)

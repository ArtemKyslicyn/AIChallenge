"""HTTP capture client for the private ops-console ingest API.

Failures are logged and swallowed: analytics must never break chat.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.domain.analytics import AnalyticsCapture, AnalyticsEvent

logger = logging.getLogger(__name__)


class NoOpAnalyticsCapture:
    async def capture(self, events: list[AnalyticsEvent]) -> None:
        return None

    async def aclose(self) -> None:
        return None


class HttpAnalyticsCapture:
    def __init__(
        self,
        *,
        capture_url: str,
        ingest_key: str,
        product_id: str,
        timeout_seconds: float = 2.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = capture_url.rstrip("/")
        self._key = ingest_key
        self._product_id = product_id
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def capture(self, events: list[AnalyticsEvent]) -> None:
        if not events:
            return
        batch: list[dict[str, Any]] = []
        for event in events:
            item: dict[str, Any] = {
                "event": event.name,
                "distinct_id": event.distinct_id or "anonymous",
                "product_id": self._product_id,
                "properties": dict(event.properties),
                "source": "api",
            }
            if event.timestamp is not None:
                item["timestamp"] = event.timestamp.isoformat()
            batch.append(item)
        try:
            response = await self._client.post(
                self._url,
                json={"batch": batch},
                headers={"X-Ingest-Key": self._key, "Content-Type": "application/json"},
            )
            if response.status_code >= 400:
                logger.warning(
                    "analytics capture rejected status=%s count=%s",
                    response.status_code,
                    len(batch),
                )
        except Exception:
            logger.warning("analytics capture failed count=%s", len(batch), exc_info=True)

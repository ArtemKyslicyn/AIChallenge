from __future__ import annotations

import httpx
import pytest

from app.adapters.analytics.http_capture import HttpAnalyticsCapture, NoOpAnalyticsCapture
from app.domain.analytics import AnalyticsEvent


@pytest.mark.asyncio
async def test_noop_capture_is_silent() -> None:
    sink = NoOpAnalyticsCapture()
    await sink.capture([AnalyticsEvent(name="message_sent", distinct_id="v1")])
    await sink.aclose()


@pytest.mark.asyncio
async def test_http_capture_posts_batch_with_ingest_key() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers.get("X-Ingest-Key")
        seen["body"] = request.read()
        return httpx.Response(200, json={"status": "ok", "accepted": 1})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://ops.test")
    sink = HttpAnalyticsCapture(
        capture_url="http://ops.test/v1/capture",
        ingest_key="secret-ingest",
        product_id="aichallenge",
        client=client,
    )
    await sink.capture(
        [
            AnalyticsEvent(
                name="assistant_completed",
                distinct_id="vh",
                properties={"model_id": "m1", "session_id": "s1"},
            )
        ]
    )
    await sink.aclose()
    assert seen["path"] == "/v1/capture"
    assert seen["key"] == "secret-ingest"
    body = seen["body"]
    assert isinstance(body, bytes)
    assert b"assistant_completed" in body
    assert b"aichallenge" in body


@pytest.mark.asyncio
async def test_http_capture_swallows_transport_errors() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(boom), base_url="http://ops.test")
    sink = HttpAnalyticsCapture(
        capture_url="http://ops.test/v1/capture",
        ingest_key="k",
        product_id="aichallenge",
        client=client,
    )
    await sink.capture([AnalyticsEvent(name="message_sent", distinct_id="v")])
    await sink.aclose()

"""Maps chat events onto the SSE wire format."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from app.application.chat import (
    ChatEvent,
    ErrorEvent,
    MessageEndEvent,
    ModelEvent,
    TokenEvent,
)

SSE_MEDIA_TYPE = "text/event-stream"

#: X-Accel-Buffering tells nginx not to sit on the stream; without it tokens
#: arrive in one burst at the end.
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def format_frame(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def event_to_frame(event: ChatEvent) -> str:
    match event:
        case ModelEvent():
            return format_frame("model", {"model_id": event.model_id})
        case TokenEvent():
            return format_frame("token", {"text": event.text})
        case MessageEndEvent():
            return format_frame(
                "message_end",
                {
                    "message_id": str(event.message_id),
                    "content": event.content,
                    "model_id": event.model_id,
                },
            )
        case ErrorEvent():
            return format_frame("error", {"message": event.message})


async def to_sse(events: AsyncIterator[ChatEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield event_to_frame(event)

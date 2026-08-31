import json
from uuid import UUID

from app.adapters.api.sse import SSE_HEADERS, event_to_frame, to_sse
from app.application.chat import ErrorEvent, MessageEndEvent, ModelEvent, TokenEvent


def _parse(frame: str) -> tuple[str, dict]:
    assert frame.endswith("\n\n")
    name_line, data_line = frame.rstrip("\n").split("\n")
    assert name_line.startswith("event: ")
    assert data_line.startswith("data: ")
    return name_line[len("event: ") :], json.loads(data_line[len("data: ") :])


def test_model_frame() -> None:
    assert _parse(event_to_frame(ModelEvent(model_id="m-1"))) == ("model", {"model_id": "m-1"})


def test_token_frame_keeps_whitespace_and_unicode() -> None:
    name, data = _parse(event_to_frame(TokenEvent(text="привет ")))
    assert (name, data) == ("token", {"text": "привет "})


def test_token_frame_escapes_newlines_rather_than_breaking_the_frame() -> None:
    frame = event_to_frame(TokenEvent(text="a\nb"))
    # A raw newline inside data would terminate the event early.
    assert frame.count("\n") == 3
    assert _parse(frame)[1] == {"text": "a\nb"}


def test_message_end_frame_carries_canonical_attribution() -> None:
    event = MessageEndEvent(message_id=UUID(int=1), content="hi", model_id="m-1")
    name, data = _parse(event_to_frame(event))
    assert name == "message_end"
    assert data == {"message_id": str(UUID(int=1)), "content": "hi", "model_id": "m-1"}


def test_error_frame() -> None:
    assert _parse(event_to_frame(ErrorEvent(message="nope"))) == ("error", {"message": "nope"})


def test_headers_disable_proxy_buffering() -> None:
    assert SSE_HEADERS["X-Accel-Buffering"] == "no"
    assert "no-cache" in SSE_HEADERS["Cache-Control"]


async def test_to_sse_streams_every_event() -> None:
    async def events():
        yield ModelEvent(model_id="m-1")
        yield TokenEvent(text="hi")

    frames = [f async for f in to_sse(events())]
    assert [_parse(f)[0] for f in frames] == ["model", "token"]

from starlette.requests import Request

from app.adapters.api.media import _content_response


def _request(*, range_header: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if range_header:
        headers.append((b"range", range_header.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/media/x.mp4",
        "raw_path": b"/api/v1/media/x.mp4",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    return Request(scope)


def test_full_get_sets_accept_ranges():
    body = b"0123456789"
    resp = _content_response(body, "video/mp4", request=_request())
    assert resp.status_code == 200
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.body == body


def test_partial_content_range():
    body = b"0123456789"
    resp = _content_response(body, "video/mp4", request=_request(range_header="bytes=2-5"))
    assert resp.status_code == 206
    assert resp.headers["content-range"] == "bytes 2-5/10"
    assert resp.body == b"2345"


def test_open_ended_range():
    body = b"0123456789"
    resp = _content_response(body, "video/mp4", request=_request(range_header="bytes=8-"))
    assert resp.status_code == 206
    assert resp.body == b"89"
    assert resp.headers["content-range"] == "bytes 8-9/10"

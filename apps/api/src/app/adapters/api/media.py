"""Public media file serving (opaque UUID paths)."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response

from app.core.deps import get_container
from app.domain.errors import MediaNotFoundError

router = APIRouter(prefix="/media", tags=["media"])

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def _content_response(content: bytes, media_type: str, *, request: Request) -> Response:
    """Serve bytes with Accept-Ranges / optional 206 Partial Content for <video>.

    Pass the real body even for HEAD: Starlette strips the body on HEAD while
    keeping Content-Length, so clients do not hang waiting for bytes.
    """
    size = len(content)
    headers = {
        "Cache-Control": "public, max-age=86400",
        "Accept-Ranges": "bytes",
    }
    range_header = request.headers.get("range")
    if not range_header:
        return Response(
            content=content,
            status_code=200,
            media_type=media_type,
            headers=headers,
        )

    match = _RANGE.fullmatch(range_header.strip())
    if not match:
        raise HTTPException(status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)

    start_s, end_s = match.group(1), match.group(2)
    if start_s == "" and end_s == "":
        raise HTTPException(status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)

    if start_s == "":
        length = int(end_s)
        if length <= 0:
            raise HTTPException(status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
        start = max(0, size - length)
        end = size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else size - 1

    if start >= size or start < 0 or end < start:
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{size}"},
        )
    end = min(end, size - 1)
    chunk = content[start : end + 1]
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return Response(
        content=chunk,
        status_code=206,
        media_type=media_type,
        headers=headers,
    )


async def _load_media(request: Request, media_filename: str) -> tuple[bytes, str]:
    container = get_container(request)
    if container.media_store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Медиа отключено.")
    try:
        row = await container.media_store.get(media_filename)
    except MediaNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Медиа не найдено.")
    return row


@router.api_route("/{media_filename}", methods=["GET", "HEAD"])
async def get_media(media_filename: str, request: Request) -> Response:
    content, media_type = await _load_media(request, media_filename)
    return _content_response(content, media_type, request=request)

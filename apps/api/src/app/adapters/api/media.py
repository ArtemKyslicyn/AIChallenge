"""Public media file serving (opaque UUID paths)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response

from app.core.deps import get_container
from app.domain.errors import MediaNotFoundError

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{media_filename}")
async def get_media(media_filename: str, request: Request) -> Response:
    container = get_container(request)
    if container.media_store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Медиа отключено.")
    try:
        row = await container.media_store.get(media_filename)
    except MediaNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Медиа не найдено.")
    content, media_type = row
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )

"""Composite MediaGenerator + on-disk MediaStore."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

from app.adapters.media.pixazo import PixazoVideoClient
from app.adapters.media.pollinations import PollinationsImageClient
from app.domain.errors import MediaGenerationError, MediaNotFoundError
from app.domain.media import MediaArtifact, StoredMedia


class CompositeMediaGenerator:
    """Routes image → Pollinations, video → Pixazo (or raises if no key)."""

    def __init__(
        self,
        *,
        images: PollinationsImageClient,
        videos: PixazoVideoClient | None,
    ) -> None:
        self._images = images
        self._videos = videos

    async def aclose(self) -> None:
        await self._images.aclose()
        if self._videos is not None:
            await self._videos.aclose()

    async def generate_image(
        self,
        prompt: str,
        *,
        model: str = "flux",
        width: int = 1024,
        height: int = 1024,
    ) -> MediaArtifact:
        return await self._images.generate_image(prompt, model=model, width=width, height=height)

    async def generate_video(self, prompt: str) -> MediaArtifact:
        if self._videos is None:
            raise MediaGenerationError("Видео недоступно: нет PIXAZO_API_KEY.")
        return await self._videos.generate_video(prompt)


class DiskMediaStore:
    def __init__(self, root: Path, *, public_prefix: str = "/api/v1/media") -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._prefix = public_prefix.rstrip("/")
        self._meta: dict[UUID, tuple[str, str, str]] = {}

    async def save(self, artifact: MediaArtifact) -> StoredMedia:
        media_id = uuid4()
        path = self._root / f"{media_id}{artifact.extension}"

        def _write() -> None:
            path.write_bytes(artifact.content)

        await asyncio.to_thread(_write)
        self._meta[media_id] = (artifact.media_type, artifact.extension, artifact.provider_label)
        return StoredMedia(
            id=media_id,
            media_type=artifact.media_type,
            extension=artifact.extension,
            provider_label=artifact.provider_label,
            public_path=f"{self._prefix}/{media_id}{artifact.extension}",
        )

    async def get(self, media_id: object) -> tuple[bytes, str] | None:
        raw = str(media_id)
        # Accept both bare UUID and UUID.ext from public URLs.
        stem = raw.split(".", 1)[0]
        try:
            uid = media_id if isinstance(media_id, UUID) else UUID(stem)
        except (TypeError, ValueError) as exc:
            raise MediaNotFoundError("Медиа не найдено.") from exc

        matches = list(self._root.glob(f"{uid}.*"))
        if not matches:
            return None
        path = matches[0]

        def _read() -> bytes:
            return path.read_bytes()

        content = await asyncio.to_thread(_read)
        meta = self._meta.get(uid)
        if meta:
            return content, meta[0]
        if path.suffix.lower() in {".mp4", ".webm"}:
            return content, "video/mp4"
        if path.suffix.lower() == ".png":
            return content, "image/png"
        return content, "image/jpeg"

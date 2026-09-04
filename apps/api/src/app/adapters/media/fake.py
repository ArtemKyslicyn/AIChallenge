"""Deterministic media generator for tests and keyless CI."""

from __future__ import annotations

from app.domain.errors import MediaGenerationError
from app.domain.media import MediaArtifact

# Minimal JPEG SOI/EOI pair — enough for content-type checks in unit tests.
_TINY_JPEG = b"\xff\xd8\xff\xd9"
_TINY_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"


class FakeMediaGenerator:
    def __init__(self, *, fail_video: bool = False) -> None:
        self.fail_video = fail_video
        self.image_calls: list[tuple[str, str]] = []
        self.video_calls: list[str] = []

    async def generate_image(
        self,
        prompt: str,
        *,
        model: str = "flux",
        width: int = 1024,
        height: int = 1024,
        seed: int | None = None,
    ) -> MediaArtifact:
        _ = width, height, seed
        clean = " ".join((prompt or "").split())
        if not clean:
            raise MediaGenerationError("Пустой промпт для картинки.")
        self.image_calls.append((clean, model))
        return MediaArtifact(
            content=_TINY_JPEG,
            media_type="image/jpeg",
            extension=".jpg",
            provider_label=f"Fake Pollinations {model}",
        )

    async def generate_video(self, prompt: str) -> MediaArtifact:
        clean = " ".join((prompt or "").split())
        if not clean:
            raise MediaGenerationError("Пустой промпт для видео.")
        if self.fail_video:
            raise MediaGenerationError("Видео недоступно: нет PIXAZO_API_KEY.")
        self.video_calls.append(clean)
        return MediaArtifact(
            content=_TINY_MP4,
            media_type="video/mp4",
            extension=".mp4",
            provider_label="Fake Pixazo LTX",
        )

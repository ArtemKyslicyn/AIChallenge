"""Pollinations free image (and optional keyed gen) adapter."""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

from app.domain.errors import MediaGenerationError
from app.domain.media import MediaArtifact

logger = logging.getLogger(__name__)

LEGACY_IMAGE_BASE = "https://image.pollinations.ai/prompt"
GEN_IMAGE_BASE = "https://gen.pollinations.ai/image"
DEFAULT_TIMEOUT_SECONDS = 180.0


class PollinationsImageClient:
    def __init__(
        self,
        *,
        api_key: str = "",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {"Authorization": f"Bearer {self._api_key}"}

    async def generate_image(
        self,
        prompt: str,
        *,
        model: str = "flux",
        width: int = 1024,
        height: int = 1024,
        seed: int | None = None,
    ) -> MediaArtifact:
        clean = " ".join((prompt or "").split())
        if not clean:
            raise MediaGenerationError("Пустой промпт для картинки.")
        # Long path segments get truncated/ignored by CDNs and Flux.
        if len(clean) > 900:
            clean = clean[:899].rsplit(" ", 1)[0] + "…"
        encoded = quote(clean, safe="")
        params = [
            f"model={quote(str(model or 'flux'))}",
            f"width={max(64, min(int(width), 2048))}",
            f"height={max(64, min(int(height), 2048))}",
            "nologo=true",
        ]
        if seed is not None:
            params.append(f"seed={int(seed)}")
        query = "&".join(params)
        urls: list[str] = []
        if self._api_key:
            urls.append(f"{GEN_IMAGE_BASE}/{encoded}?{query}")
        urls.append(f"{LEGACY_IMAGE_BASE}/{encoded}?{query}")

        last_error = "no response"
        for url in urls:
            try:
                response = await self._client.get(url, headers=self._headers())
            except httpx.HTTPError as exc:
                last_error = str(exc)
                continue
            body = response.content
            if response.status_code >= 400:
                last_error = body[:200].decode("utf-8", "replace") or str(response.status_code)
                continue
            ctype = (response.headers.get("Content-Type") or "").split(";")[0].strip()
            if not ctype.startswith("image/") and not body.startswith(b"\xff\xd8"):
                last_error = body[:200].decode("utf-8", "replace") or "not an image"
                continue
            media_type = ctype if ctype.startswith("image/") else "image/jpeg"
            ext = ".png" if "png" in media_type else ".jpg"
            return MediaArtifact(
                content=body,
                media_type=media_type,
                extension=ext,
                provider_label=f"Pollinations {model or 'flux'}",
            )
        raise MediaGenerationError(f"Не удалось сгенерировать картинку: {last_error}")

"""Pixazo free LTX text-to-video adapter."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.domain.errors import MediaGenerationError
from app.domain.media import MediaArtifact

logger = logging.getLogger(__name__)

GATEWAY = "https://gateway.pixazo.ai"
FREE_T2V_URL = f"{GATEWAY}/ltx-video/v1/text-to-video"
STATUS_URL = f"{GATEWAY}/v2/requests/status"
DEFAULT_TIMEOUT_SECONDS = 600.0
POLL_SECONDS = 5.0


class PixazoVideoClient:
    def __init__(
        self,
        *,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        poll_seconds: float = POLL_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._timeout = timeout
        self._poll_seconds = poll_seconds
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise MediaGenerationError("Видео недоступно: нет PIXAZO_API_KEY.")
        return {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "Ocp-Apim-Subscription-Key": self._api_key,
            "User-Agent": "AIChallenge/1.0",
        }

    async def generate_video(self, prompt: str) -> MediaArtifact:
        clean = " ".join((prompt or "").split())
        if not clean:
            raise MediaGenerationError("Пустой промпт для видео.")
        headers = self._headers()
        try:
            response = await self._client.post(
                FREE_T2V_URL, headers=headers, json={"prompt": clean}
            )
        except httpx.HTTPError as exc:
            raise MediaGenerationError(f"Pixazo недоступен: {exc}") from exc
        if response.status_code >= 400:
            raise MediaGenerationError(
                response.text[:300] or f"Pixazo HTTP {response.status_code}"
            )
        try:
            payload: dict[str, Any] = response.json()
        except Exception as exc:
            raise MediaGenerationError("Pixazo вернул нечитаемый ответ.") from exc

        request_id = str(payload.get("request_id") or "").strip()
        poll_url = str(payload.get("polling_url") or "").strip()
        if not request_id:
            raise MediaGenerationError("Pixazo не вернул request_id.")
        if not poll_url:
            poll_url = f"{STATUS_URL}/{request_id}"

        deadline = asyncio.get_running_loop().time() + self._timeout
        status_payload: dict[str, Any] = {}
        while asyncio.get_running_loop().time() < deadline:
            try:
                status_resp = await self._client.get(poll_url, headers=headers)
            except httpx.HTTPError as exc:
                raise MediaGenerationError(f"Pixazo status failed: {exc}") from exc
            if status_resp.status_code >= 400:
                raise MediaGenerationError(
                    status_resp.text[:300] or f"Pixazo status HTTP {status_resp.status_code}"
                )
            status_payload = status_resp.json()
            status = str(status_payload.get("status") or "").upper()
            if status in {"COMPLETED", "SUCCEEDED", "SUCCESS"}:
                break
            if status in {"FAILED", "ERROR", "CANCELLED", "CANCELED"}:
                raise MediaGenerationError(
                    str(status_payload.get("error") or status_payload)[:300]
                )
            await asyncio.sleep(self._poll_seconds)
        else:
            raise MediaGenerationError("Генерация видео превысила время ожидания.")

        output = status_payload.get("output") or {}
        urls = output.get("media_url") if isinstance(output, dict) else None
        if not isinstance(urls, list) or not urls:
            raise MediaGenerationError("Pixazo завершился без media_url.")
        media_url = str(urls[0])
        try:
            media_resp = await self._client.get(media_url)
        except httpx.HTTPError as exc:
            raise MediaGenerationError(f"Не удалось скачать видео: {exc}") from exc
        if media_resp.status_code >= 400 or not media_resp.content:
            raise MediaGenerationError(f"Скачивание видео HTTP {media_resp.status_code}.")
        ctype = (media_resp.headers.get("Content-Type") or "video/mp4").split(";")[0]
        return MediaArtifact(
            content=media_resp.content,
            media_type=ctype if ctype.startswith("video/") else "video/mp4",
            extension=".mp4",
            provider_label="Pixazo LTX",
        )

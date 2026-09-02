"""Media tool schemas, intent fallback, and execution helpers."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.domain.errors import MediaGenerationError, MediaRateLimitError
from app.domain.media import (
    IMAGE_TOOL_NAME,
    MEDIA_TOOL_SCHEMAS,
    VIDEO_TOOL_NAME,
    ToolCallRequest,
)
from app.domain.ports import MediaGenerator, MediaStore

_IMAGE_HINT = re.compile(
    r"(?i)(?:нарисуй|сгенер(?:ируй|ировать)\s+(?:картинк|изображен)|"
    r"сделай\s+(?:картинк|изображен|рисунок)|"
    r"(?:generate|draw|paint|create)\s+(?:an?\s+)?(?:image|picture|drawing)|"
    r"/pollinations\b)"
)
_VIDEO_HINT = re.compile(
    r"(?i)(?:сделай\s+(?:коротк\w+\s+)?видео|сгенер(?:ируй|ировать)\s+видео|"
    r"(?:generate|make|create)\s+(?:a\s+)?(?:short\s+)?video|"
    r"/pixazo\b)"
)
_SOFT_MEDIA = re.compile(
    r"(?i)(?:картинк|изображен|рисунок|image|picture|drawing|видео|video|"
    r"нарис|draw|visuali[sz]|pollinations|pixazo)"
)
_PROMPT_STRIP = re.compile(
    r"(?i)^(?:пожалуйста[, ]*)?(?:нарисуй|сгенер(?:ируй|ировать)|сделай|"
    r"generate|draw|paint|create|make)\s+"
    r"(?:(?:мне|please)\s+)?(?:(?:an?|the|коротк\w+|short)\s+)?"
    r"(?:картинк\w*|изображен\w*|рисунок|image|picture|drawing|видео|video)?\s*"
    r"(?:of\s+|с\s+|про\s+|на\s+|с\s+темой\s+)?",
)


@dataclass(slots=True)
class ExecutedTool:
    call: ToolCallRequest
    media_url: str | None
    provider_label: str | None
    markdown: str
    error: str | None = None


def maybe_needs_media_tools(text: str) -> bool:
    """Cheap gate before spending a complete_chat tools probe."""
    return bool(_SOFT_MEDIA.search(text or ""))


def detect_media_intent(text: str) -> list[ToolCallRequest]:
    """Keyword fallback when the chat model does not emit tool_calls."""
    clean = " ".join((text or "").split())
    if not clean:
        return []
    # Composer may append response-template rules; keep only the user wording.
    for marker in ("\n\nУсловие завершения:", "\nУсловие завершения:", " — Условие завершения:"):
        if marker in clean:
            clean = clean.split(marker, 1)[0].strip()
    for marker in ("AI Challenge —", "Как отвечать"):
        if marker in clean and clean.index(marker) > 8:
            # Template was appended after the user prompt.
            clean = clean.split(marker, 1)[0].strip(" —-\n")
    calls: list[ToolCallRequest] = []
    prompt = _PROMPT_STRIP.sub("", clean).strip(" .,!:;—-") or clean
    if _VIDEO_HINT.search(clean):
        calls.append(
            ToolCallRequest(
                id=f"intent-{uuid4().hex[:8]}",
                name=VIDEO_TOOL_NAME,
                arguments={"prompt": prompt},
            )
        )
    elif _IMAGE_HINT.search(clean):
        model = "flux"
        lower = clean.casefold()
        for name in ("sana", "turbo", "flux"):
            if re.search(rf"\b{name}\b", lower):
                model = name
                break
        calls.append(
            ToolCallRequest(
                id=f"intent-{uuid4().hex[:8]}",
                name=IMAGE_TOOL_NAME,
                arguments={"prompt": prompt, "model": model},
            )
        )
    return calls


def tool_calls_from_completion(raw: list[ToolCallRequest] | None) -> list[ToolCallRequest]:
    return list(raw or [])


def media_markdown(*, kind: str, url: str, alt: str, provider_label: str) -> str:
    if kind == "video":
        return f"[{alt or 'Видео'}]({url}) · {provider_label}"
    return f"![{alt or 'Изображение'}]({url})\n\n_{provider_label}_"


class SessionMediaRateLimiter:
    """In-process per-session hourly caps."""

    def __init__(self, *, image_limit: int, video_limit: int) -> None:
        self._image_limit = max(0, image_limit)
        self._video_limit = max(0, video_limit)
        self._image: dict[str, list[float]] = defaultdict(list)
        self._video: dict[str, list[float]] = defaultdict(list)

    def _prune(self, stamps: list[float], now: float) -> list[float]:
        cutoff = now - 3600.0
        return [t for t in stamps if t >= cutoff]

    def check(self, session_id: UUID, tool_name: str) -> None:
        now = time.monotonic()
        key = str(session_id)
        if tool_name == IMAGE_TOOL_NAME:
            stamps = self._prune(self._image[key], now)
            self._image[key] = stamps
            if self._image_limit and len(stamps) >= self._image_limit:
                raise MediaRateLimitError(
                    f"Лимит картинок: не больше {self._image_limit} в час для этой сессии."
                )
        elif tool_name == VIDEO_TOOL_NAME:
            stamps = self._prune(self._video[key], now)
            self._video[key] = stamps
            if self._video_limit and len(stamps) >= self._video_limit:
                raise MediaRateLimitError(
                    f"Лимит видео: не больше {self._video_limit} в час для этой сессии."
                )

    def record(self, session_id: UUID, tool_name: str) -> None:
        now = time.monotonic()
        key = str(session_id)
        if tool_name == IMAGE_TOOL_NAME:
            self._image[key] = self._prune(self._image[key], now) + [now]
        elif tool_name == VIDEO_TOOL_NAME:
            self._video[key] = self._prune(self._video[key], now) + [now]


async def execute_media_tool(
    call: ToolCallRequest,
    *,
    generator: MediaGenerator,
    store: MediaStore,
    session_id: UUID,
    limiter: SessionMediaRateLimiter,
) -> ExecutedTool:
    limiter.check(session_id, call.name)
    args = call.arguments if isinstance(call.arguments, dict) else {}
    prompt = str(args.get("prompt") or "").strip()
    try:
        if call.name == IMAGE_TOOL_NAME:
            model = str(args.get("model") or "flux").strip() or "flux"
            artifact = await generator.generate_image(prompt, model=model)
            kind = "image"
        elif call.name == VIDEO_TOOL_NAME:
            artifact = await generator.generate_video(prompt)
            kind = "video"
        else:
            raise MediaGenerationError(f"Неизвестный tool: {call.name}")
        stored = await store.save(artifact)
        limiter.record(session_id, call.name)
        md = media_markdown(
            kind=kind,
            url=stored.public_path,
            alt=prompt[:80] or kind,
            provider_label=artifact.provider_label,
        )
        return ExecutedTool(
            call=call,
            media_url=stored.public_path,
            provider_label=artifact.provider_label,
            markdown=md,
        )
    except (MediaGenerationError, MediaRateLimitError) as exc:
        return ExecutedTool(
            call=call,
            media_url=None,
            provider_label=None,
            markdown="",
            error=str(exc),
        )
    except OSError as exc:
        return ExecutedTool(
            call=call,
            media_url=None,
            provider_label=None,
            markdown="",
            error=f"Не удалось сохранить медиа: {exc}",
        )


MEDIA_TOOLS = MEDIA_TOOL_SCHEMAS

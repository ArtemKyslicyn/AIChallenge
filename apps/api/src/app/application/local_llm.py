"""Connect one Ollama origin per signed-in user. Tags are injected."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID

from app.domain.entities import AUTO_MODEL
from app.domain.errors import LLMProviderError
from app.domain.local_llm import (
    LOCAL_LLM_PREFIX,
    LocalLlmRepository,
    LocalLlmSource,
    LocalLlmUrlError,
    canonical_model_id,
    reset_local_llm_source,
    set_local_llm_source,
    validate_ollama_origin,
)

UNREACHABLE = "Ollama недоступен по этому адресу."

TagsFn = Callable[[str, str | None], Awaitable[tuple[str, ...]]]


class _Policy(Protocol):
    local_llm_allow_loopback: bool
    local_llm_allow_tailscale: bool
    local_llm_allow_private: bool
    local_llm_origin_allowlist: str


@dataclass(frozen=True, slots=True)
class LocalLlmPublic:
    name: str
    base_host: str
    status: str
    models: tuple[str, ...]
    enabled: bool


def to_public(source: LocalLlmSource) -> LocalLlmPublic:
    return LocalLlmPublic(
        name=source.name,
        base_host=(urlparse(source.base_url).hostname or ""),
        status=source.status,
        models=source.models,
        enabled=source.enabled,
    )


def validate_stored_origin(source: LocalLlmSource, settings: _Policy) -> LocalLlmSource | None:
    """Re-check a DB row against current policy. Drop the row from scope if stale."""
    if not source.enabled or source.status != "connected":
        return None
    try:
        validate_ollama_origin(
            source.base_url,
            allow_loopback=bool(settings.local_llm_allow_loopback),
            allow_tailscale=bool(settings.local_llm_allow_tailscale),
            allow_private=bool(settings.local_llm_allow_private),
            origin_allowlist_csv=str(settings.local_llm_origin_allowlist or ""),
        )
    except LocalLlmUrlError:
        return None
    return source


async def connect_local_llm(
    user_id: UUID,
    *,
    name: str,
    base_url: str,
    api_key: str | None,
    settings: _Policy,
    repo: LocalLlmRepository,
    tags: TagsFn,
) -> LocalLlmPublic:
    cleaned = name.strip()
    if not cleaned:
        raise LocalLlmUrlError("Укажите название.")
    origin = validate_ollama_origin(
        base_url,
        allow_loopback=bool(settings.local_llm_allow_loopback),
        allow_tailscale=bool(settings.local_llm_allow_tailscale),
        allow_private=bool(settings.local_llm_allow_private),
        origin_allowlist_csv=str(settings.local_llm_origin_allowlist or ""),
    )
    secret = (api_key or "").strip() or None
    try:
        models = await tags(origin, secret)
    except LLMProviderError as exc:
        raise LLMProviderError(
            UNREACHABLE,
            kind=exc.kind or "transport",
            status=exc.status,
        ) from exc
    except Exception as exc:
        raise LLMProviderError(UNREACHABLE, kind="transport") from exc
    source = LocalLlmSource(
        user_id=user_id,
        name=cleaned[:80],
        base_url=origin,
        api_key=secret,
        enabled=True,
        models=tuple(models),
        status="connected",
        safe_error=None,
    )
    await repo.upsert(source)
    return to_public(source)


async def disconnect_local_llm(user_id: UUID, repo: LocalLlmRepository) -> None:
    await repo.delete_for_user(user_id)


@asynccontextmanager
async def local_llm_scope(source: LocalLlmSource | None) -> AsyncIterator[None]:
    token = set_local_llm_source(source if source and source.enabled else None)
    try:
        yield
    finally:
        reset_local_llm_source(token)


def prefer_local_model(
    requested: str | None,
    *,
    local_model_ids: list[str],
) -> str:
    """Honor an explicit pin; when auto/empty, default to the first connected ollama/ id."""
    pin = (requested or "").strip() or AUTO_MODEL
    if pin != AUTO_MODEL:
        return pin
    for mid in local_model_ids:
        if mid.startswith(LOCAL_LLM_PREFIX):
            return mid
    for tag_or_id in local_model_ids:
        try:
            return canonical_model_id(tag_or_id)
        except LocalLlmUrlError:
            continue
    return AUTO_MODEL

"""Composition root: builds adapters from settings and hands them to routes."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.adapters.llm.fake import DEFAULT_FAKE_MODEL_ID, FakeLLMProvider
from app.adapters.llm.openai_compatible import OpenAICompatibleProvider
from app.adapters.llm.router import ModelRouter, TieredModelRouter
from app.adapters.media.fake import FakeMediaGenerator
from app.adapters.media.pixazo import PixazoVideoClient
from app.adapters.media.pollinations import PollinationsImageClient
from app.adapters.media.store import CompositeMediaGenerator, DiskMediaStore
from app.adapters.persistence.db import create_engine, create_sessionmaker
from app.adapters.persistence.repositories import SqlAlchemySessionRepository
from app.adapters.scenarios.yaml_repo import YamlScenarioRepository
from app.application.media_tools import SessionMediaRateLimiter
from app.application.sessions import authorize_session
from app.core.settings import Settings
from app.core.visitor import client_ip_from_headers, hash_ip, normalize_visitor_id, visitor_hash
from app.domain.entities import Session
from app.domain.errors import SessionNotFoundError
from app.domain.ports import LLMProvider, MediaGenerator, MediaStore, ScenarioRepository

logger = logging.getLogger(__name__)

SESSION_TOKEN_HEADER = "X-Session-Token"
VISITOR_ID_HEADER = "X-Visitor-Id"

#: Strong references to work that must outlive a cancelled request.
_detached: set[asyncio.Task[None]] = set()


async def run_shielded(work: Coroutine[object, object, None]) -> None:
    """Run ``work`` to completion even if the current task is being cancelled.

    Everything a disconnecting client leaves behind — saving the partial answer,
    returning the connection to the pool — has to survive the cancellation that
    the disconnect itself causes.
    """
    task = asyncio.create_task(work)
    _detached.add(task)
    task.add_done_callback(_detached.discard)
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.shield(task)


async def close_quietly(db: AsyncSession) -> None:
    """Return the connection to the pool even while being cancelled.

    Without this, ``close()`` is cancelled along with the request and the
    connection is abandoned until the garbage collector terminates it — a leak
    on every client disconnect.
    """
    await run_shielded(db.close())


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    provider: LLMProvider
    router: ModelRouter | TieredModelRouter
    scenarios: ScenarioRepository
    media_generator: MediaGenerator | None
    media_store: MediaStore | None
    media_limiter: SessionMediaRateLimiter | None
    _extra_providers: list[LLMProvider]
    _extra_closers: list[object]

    async def aclose(self) -> None:
        for provider in (self.provider, *self._extra_providers):
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()
        for item in self._extra_closers:
            close = getattr(item, "aclose", None)
            if close is not None:
                await close()
        await self.engine.dispose()


def _openai_provider(
    settings: Settings,
    *,
    base_url: str,
    api_key: str,
    proxy: str | None,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url,
        api_key,
        proxy=proxy,
        extra_headers={
            "HTTP-Referer": settings.llm_http_referer,
            "X-Title": settings.llm_app_title,
        },
    )


def _router_for(settings: Settings, provider: LLMProvider, chain: list[str]) -> ModelRouter:
    """One place for the per-request limits, so no chain can escape them."""
    return ModelRouter(
        provider,
        chain,
        exhausted_ttl_seconds=settings.llm_exhausted_ttl_seconds,
        max_attempts=settings.llm_max_attempts,
        first_token_timeout_seconds=settings.llm_first_token_timeout_seconds,
    )


def build_container(settings: Settings) -> Container:
    provider: LLMProvider
    extra_providers: list[LLMProvider] = []
    if settings.fake_llm_enabled():
        provider = FakeLLMProvider()
        chain = settings.model_chain_list() or [DEFAULT_FAKE_MODEL_ID]
        router: ModelRouter | TieredModelRouter = _router_for(settings, provider, chain)
        logger.info("using FakeLLMProvider (no provider key configured)")
    else:
        primary_proxy = settings.llm_http_proxy.strip() or None
        if primary_proxy:
            logger.info("LLM outbound proxy enabled for primary tier")
        provider = _openai_provider(
            settings,
            base_url=settings.llm_base_url,
            api_key=settings.primary_llm_api_key(),
            proxy=primary_proxy,
        )
        chain = settings.model_chain_list()
        if not chain:
            raise RuntimeError(
                "LLM_MODEL_CHAIN must list at least one model id when LLM_API_KEY is set."
            )
        primary_router = _router_for(settings, provider, chain)
        if settings.llm_fallback_enabled():
            fallback_proxy = settings.llm_fallback_http_proxy.strip() or None
            fallback_provider = _openai_provider(
                settings,
                base_url=settings.llm_fallback_base_url,
                api_key=settings.resolved_fallback_api_key(),
                proxy=fallback_proxy,
            )
            extra_providers.append(fallback_provider)
            fallback_router = _router_for(
                settings, fallback_provider, settings.fallback_chain_list()
            )
            router = TieredModelRouter([primary_router, fallback_router])
            logger.info("LLM tiered router enabled (primary + fallback provider)")
        else:
            router = primary_router

    media_generator: MediaGenerator | None = None
    media_store: MediaStore | None = None
    media_limiter: SessionMediaRateLimiter | None = None
    extra_closers: list[object] = []
    if settings.media_tools_enabled:
        media_store = DiskMediaStore(settings.media_path())
        media_limiter = SessionMediaRateLimiter(
            image_limit=settings.media_image_limit_per_hour,
            video_limit=settings.media_video_limit_per_hour,
        )
        if settings.fake_llm_enabled():
            media_generator = FakeMediaGenerator(
                fail_video=not bool(settings.pixazo_api_key.strip())
            )
            logger.info("media tools enabled (FakeMediaGenerator)")
        else:
            images = PollinationsImageClient(api_key=settings.pollinations_api_key)
            videos = (
                PixazoVideoClient(api_key=settings.pixazo_api_key)
                if settings.pixazo_api_key.strip()
                else None
            )
            media_generator = CompositeMediaGenerator(images=images, videos=videos)
            extra_closers.append(media_generator)
            logger.info(
                "media tools enabled (Pollinations%s)",
                " + Pixazo" if videos is not None else "",
            )

    engine = create_engine(settings.database_url)
    return Container(
        settings=settings,
        engine=engine,
        sessionmaker=create_sessionmaker(engine),
        provider=provider,
        router=router,
        scenarios=YamlScenarioRepository(settings.scenarios_path()),
        media_generator=media_generator,
        media_store=media_store,
        media_limiter=media_limiter,
        _extra_providers=extra_providers,
        _extra_closers=extra_closers,
    )


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Request-scoped session.

    Never use this for a streaming response: FastAPI closes it before the body
    finishes. Streaming routes open their own session from the sessionmaker.
    """
    container = get_container(request)
    db = container.sessionmaker()
    try:
        yield db
    finally:
        await close_quietly(db)


def session_token(
    x_session_token: Annotated[str | None, Header(alias=SESSION_TOKEN_HEADER)] = None,
) -> str | None:
    return x_session_token


def visitor_id_header(
    x_visitor_id: Annotated[str | None, Header(alias=VISITOR_ID_HEADER)] = None,
) -> str | None:
    return normalize_visitor_id(x_visitor_id)


def resolve_visitor_identity(
    request: Request,
    client_visitor_id: str | None,
) -> tuple[str, str] | None:
    """Return ``(visitor_hash, ip_hash)`` when the browser sent a valid id."""
    if not client_visitor_id:
        return None
    settings = request.app.state.settings
    ip = client_ip_from_headers(
        request.headers.get("x-forwarded-for"),
        request.client.host if request.client else None,
    )
    ip_digest = hash_ip(salt=settings.visitor_hash_salt, ip=ip)
    return (
        visitor_hash(
            salt=settings.visitor_hash_salt,
            client_visitor_id=client_visitor_id,
            ip=ip,
        ),
        ip_digest,
    )


async def require_visitor_hash(
    request: Request,
    client_visitor_id: Annotated[str | None, Depends(visitor_id_header)],
) -> str:
    identity = resolve_visitor_identity(request, client_visitor_id)
    if identity is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Нужен заголовок X-Visitor-Id (UUID из localStorage).",
        )
    return identity[0]


DbSession = Annotated[AsyncSession, Depends(get_db)]
SessionToken = Annotated[str | None, Depends(session_token)]


async def require_session(
    session_id: str,
    token: SessionToken,
    db: DbSession,
) -> Session:
    """Single authorization path for every session-scoped route.

    A malformed id, an unknown session, and a wrong token all return the same
    404, so the API cannot be used to discover which sessions exist.
    """
    try:
        parsed = UUID(session_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Сессия не найдена.") from None

    try:
        return await authorize_session(
            sessions=SqlAlchemySessionRepository(db), session_id=parsed, access_token=token
        )
    except SessionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Сессия не найдена.") from None


AuthorizedSession = Annotated[Session, Depends(require_session)]
VisitorHash = Annotated[str, Depends(require_visitor_hash)]

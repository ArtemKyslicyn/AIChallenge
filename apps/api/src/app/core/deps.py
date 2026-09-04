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

from app.adapters.analytics.http_capture import HttpAnalyticsCapture, NoOpAnalyticsCapture
from app.adapters.lab.rubric import load_judge_rubric
from app.adapters.llm.fake import DEFAULT_FAKE_MODEL_ID, FakeLLMProvider
from app.adapters.llm.feedback_penalties import FeedbackPenaltyCache
from app.adapters.llm.heuristic_scorer import HeuristicAnswerScorer
from app.adapters.llm.llm_judge import HourlyJudgeBudget, LLMAnswerJudge
from app.adapters.llm.openai_compatible import OpenAICompatibleProvider
from app.adapters.llm.router import ModelRouter, TieredModelRouter
from app.adapters.media.fake import FakeMediaGenerator
from app.adapters.media.pixazo import PixazoVideoClient
from app.adapters.media.pollinations import PollinationsImageClient
from app.adapters.media.store import CompositeMediaGenerator, DiskMediaStore
from app.adapters.persistence.db import create_engine, create_sessionmaker
from app.adapters.persistence.feedback_repo import SqlAlchemyFeedbackRepository
from app.adapters.persistence.repositories import (
    SqlAlchemyMessageRepository,
    SqlAlchemySessionRepository,
)
from app.adapters.persistence.trace_repo import SqlAlchemyRunTraceRepository
from app.adapters.scenarios.yaml_repo import YamlScenarioRepository
from app.application.media_tools import SessionMediaRateLimiter
from app.application.sessions import authorize_session
from app.core.settings import Settings
from app.core.visitor import client_ip_from_headers, hash_ip, normalize_visitor_id, visitor_hash
from app.domain.analytics import AnalyticsCapture
from app.domain.cascade import AnswerScorer
from app.domain.entities import Session
from app.domain.errors import SessionNotFoundError
from app.domain.ports import (
    FeedbackRepository,
    LLMProvider,
    MediaGenerator,
    MediaStore,
    MessageRepository,
    RunTraceRepository,
    ScenarioRepository,
    SessionRepository,
    UnitOfWork,
)
from app.domain.quality import AnswerJudge

logger = logging.getLogger(__name__)

SESSION_TOKEN_HEADER = "X-Session-Token"
VISITOR_ID_HEADER = "X-Visitor-Id"

#: Strong references to work that must outlive a cancelled request.
_detached: set[asyncio.Task[None]] = set()


def spawn_detached(work: Coroutine[object, object, None]) -> asyncio.Task[None]:
    """Start ``work`` in a task of its own and let go of it.

    The strong reference is the whole point: the event loop only keeps weak
    ones, so a task nobody holds can be garbage-collected mid-await.

    Used directly — without the shield below — by work that must not be waited
    for at all, such as the answer judge: it may take twenty seconds, and the
    request it measures has no business being open for them.
    """
    task = asyncio.create_task(work)
    _detached.add(task)
    task.add_done_callback(_detached.discard)
    return task


async def run_shielded(work: Coroutine[object, object, None]) -> None:
    """Run ``work`` to completion even if the current task is being cancelled.

    Everything a disconnecting client leaves behind — saving the partial answer,
    returning the connection to the pool — has to survive the cancellation that
    the disconnect itself causes.
    """
    task = spawn_detached(work)
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
    #: Shared by every router tier, refreshed once per chat request.
    penalties: FeedbackPenaltyCache
    #: Judges a cheap answer for the cascade. Stateless, so one is enough.
    scorer: AnswerScorer
    #: Resolved here rather than read from settings at call time: the keyless
    #: path substitutes a chain of its own, and the cascade must aim at the
    #: models this process actually has.
    cascade_cheap_models: list[str]
    #: ``None`` when JUDGE_MODEL is empty — the feature's off switch is the
    #: absence of the object, so no later code path can forget to check a flag.
    judge: AnswerJudge | None
    #: How much of this hour's judging budget this process has spent.
    #: In-process like the penalty cache, and asked the same way: the answer
    #: has to already be in memory when a finishing request asks for it.
    judge_budget: HourlyJudgeBudget
    #: Fail-open product analytics. Always present; may be a no-op sink.
    analytics: AnalyticsCapture
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


def _penalty_cache(settings: Settings) -> FeedbackPenaltyCache:
    return FeedbackPenaltyCache(
        min_votes=settings.feedback_min_votes,
        down_rate_threshold=settings.feedback_down_rate_threshold,
        window_seconds=settings.feedback_penalty_ttl_seconds,
        refresh_seconds=settings.feedback_penalty_refresh_seconds,
    )


def _router_for(
    settings: Settings,
    provider: LLMProvider,
    chain: list[str],
    penalties: FeedbackPenaltyCache,
) -> ModelRouter:
    """One place for the per-request limits, so no chain can escape them."""
    return ModelRouter(
        provider,
        chain,
        exhausted_ttl_seconds=settings.llm_exhausted_ttl_seconds,
        max_attempts=settings.llm_max_attempts,
        first_token_timeout_seconds=settings.llm_first_token_timeout_seconds,
        penalties=penalties,
    )


def _build_analytics(settings: Settings) -> AnalyticsCapture:
    """Capture client, or a silent no-op when URL/key are unset.

    Chat must keep working if the private ops console is down or never wired.
    """
    url = settings.analytics_capture_url.strip()
    key = settings.analytics_ingest_key.strip()
    product_id = settings.analytics_product_id.strip() or "aichallenge"
    if not url or not key:
        return NoOpAnalyticsCapture()
    logger.info("analytics capture enabled product_id=%s", product_id)
    return HttpAnalyticsCapture(
        capture_url=url,
        ingest_key=key,
        product_id=product_id,
    )


def _build_judge(settings: Settings, router: ModelRouter | TieredModelRouter) -> AnswerJudge | None:
    """The judge, or nothing at all when nobody asked for one.

    Two ways to get nothing, and both are silent about it in the chat: an empty
    ``JUDGE_MODEL`` means the operator never turned the feature on, and an
    unusable rubric means they turned it on but the file cannot be read. The
    second is worth a warning; neither is worth a failed start, because in both
    cases the product simply behaves the way it did before the judge existed.
    """
    model_id = settings.judge_model.strip()
    if not model_id:
        return None
    rubric = load_judge_rubric(settings.lab_path())
    if rubric is None:
        logger.warning("JUDGE_MODEL is set but no usable rubric was found; judge stays off")
        return None
    logger.info(
        "answer judge enabled model_id=%s sample_rate=%s max_per_hour=%s",
        model_id,
        settings.judge_sample_rate,
        settings.judge_max_per_hour,
    )
    return LLMAnswerJudge(
        router=router,
        model_id=model_id,
        rubric=rubric,
        timeout_seconds=settings.judge_timeout_seconds,
    )


def build_container(settings: Settings) -> Container:
    provider: LLMProvider
    extra_providers: list[LLMProvider] = []
    # One cache for every tier: a model's reputation does not change because a
    # different provider happens to be serving it.
    penalties = _penalty_cache(settings)
    if settings.fake_llm_enabled():
        provider = FakeLLMProvider()
        chain = settings.model_chain_list() or [DEFAULT_FAKE_MODEL_ID]
        router: ModelRouter | TieredModelRouter = _router_for(settings, provider, chain, penalties)
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
        primary_router = _router_for(settings, provider, chain, penalties)
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
                settings, fallback_provider, settings.fallback_chain_list(), penalties
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

    cheap_models = settings.cascade_cheap_models_list() or chain[:1]
    if settings.cascade_enabled:
        logger.info("cascade enabled cheap_models=%s", ",".join(cheap_models) or "<none>")

    analytics = _build_analytics(settings)
    extra_closers.append(analytics)

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
        penalties=penalties,
        scorer=HeuristicAnswerScorer(
            min_answer_chars=settings.cascade_min_answer_chars,
            threshold=settings.cascade_score_threshold,
        ),
        cascade_cheap_models=cheap_models,
        judge=_build_judge(settings, router),
        judge_budget=HourlyJudgeBudget(),
        analytics=analytics,
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


def get_run_traces(request: Request, db: DbSession) -> RunTraceRepository:
    """Read side of the run journal, as a port so tests can swap it out.

    Reading is not gated by ``RUN_TRACE_ENABLED``: switching collection off
    should stop new rows, not hide the ones already recorded. The streaming
    route builds its own instance, because it also owns its own session.
    """
    return SqlAlchemyRunTraceRepository(
        db, min_judged_runs=get_container(request).settings.judge_min_runs
    )


RunTraces = Annotated[RunTraceRepository, Depends(get_run_traces)]


def get_feedback(db: DbSession) -> FeedbackRepository:
    return SqlAlchemyFeedbackRepository(db)


def get_messages(db: DbSession) -> MessageRepository:
    return SqlAlchemyMessageRepository(db)


def get_sessions(db: DbSession) -> SessionRepository:
    return SqlAlchemySessionRepository(db)


def get_uow(db: DbSession) -> UnitOfWork:
    """The transaction boundary, named as the port the use case asks for.

    The session *is* the unit of work; giving it a name of its own is what lets
    a route be tested with in-memory repositories and no database at all.
    """
    return db


Feedback = Annotated[FeedbackRepository, Depends(get_feedback)]
Messages = Annotated[MessageRepository, Depends(get_messages)]
Sessions = Annotated[SessionRepository, Depends(get_sessions)]
Uow = Annotated[UnitOfWork, Depends(get_uow)]


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

"""Composition root: builds adapters from settings and hands them to routes."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.adapters.llm.fake import DEFAULT_FAKE_MODEL_ID, FakeLLMProvider
from app.adapters.llm.openai_compatible import OpenAICompatibleProvider
from app.adapters.llm.router import ModelRouter
from app.adapters.persistence.db import create_engine, create_sessionmaker
from app.adapters.persistence.repositories import SqlAlchemySessionRepository
from app.adapters.scenarios.yaml_repo import YamlScenarioRepository
from app.application.sessions import authorize_session
from app.core.settings import Settings
from app.domain.entities import Session
from app.domain.errors import SessionNotFoundError
from app.domain.ports import LLMProvider, ScenarioRepository

logger = logging.getLogger(__name__)

SESSION_TOKEN_HEADER = "X-Session-Token"


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    provider: LLMProvider
    router: ModelRouter
    scenarios: ScenarioRepository

    async def aclose(self) -> None:
        close = getattr(self.provider, "aclose", None)
        if close is not None:
            await close()
        await self.engine.dispose()


def build_container(settings: Settings) -> Container:
    provider: LLMProvider
    if settings.fake_llm_enabled():
        provider = FakeLLMProvider()
        chain = settings.model_chain_list() or [DEFAULT_FAKE_MODEL_ID]
        logger.info("using FakeLLMProvider (no provider key configured)")
    else:
        provider = OpenAICompatibleProvider(settings.llm_base_url, settings.llm_api_key)
        chain = settings.model_chain_list()
        if not chain:
            # Fail at startup rather than on the first user message.
            raise RuntimeError(
                "LLM_MODEL_CHAIN must list at least one model id when LLM_API_KEY is set."
            )

    engine = create_engine(settings.database_url)
    return Container(
        settings=settings,
        engine=engine,
        sessionmaker=create_sessionmaker(engine),
        provider=provider,
        router=ModelRouter(
            provider, chain, exhausted_ttl_seconds=settings.llm_exhausted_ttl_seconds
        ),
        scenarios=YamlScenarioRepository(settings.scenarios_path()),
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
    async with container.sessionmaker() as db:
        yield db


def session_token(
    x_session_token: Annotated[str | None, Header(alias=SESSION_TOKEN_HEADER)] = None,
) -> str | None:
    return x_session_token


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
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found.") from None

    try:
        return await authorize_session(
            sessions=SqlAlchemySessionRepository(db), session_id=parsed, access_token=token
        )
    except SessionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found.") from None


AuthorizedSession = Annotated[Session, Depends(require_session)]

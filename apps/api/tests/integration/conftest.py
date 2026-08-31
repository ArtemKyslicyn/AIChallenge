"""Integration fixtures: a real Postgres, migrated by Alembic.

Runs only with RUN_INTEGRATION=1. Point DATABASE_URL at the Compose database
(`docker compose up -d db`).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.settings import Settings
from app.main import create_app

API_DIR = Path(__file__).resolve().parents[2]

DEFAULT_URL = "postgresql+asyncpg://aichallenge:changeme@localhost:5432/aichallenge"


def database_url() -> str:
    return os.getenv("DATABASE_URL") or DEFAULT_URL


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    """Alembic owns the schema — never Base.metadata.create_all()."""
    url = database_url()
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    yield url


@pytest.fixture
async def engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_database)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE messages, sessions RESTART IDENTITY CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def api(engine: AsyncEngine, migrated_database: str) -> AsyncIterator[AsyncClient]:
    # use_fake_llm is forced here rather than read from the ambient .env, so the
    # suite never depends on a developer's provider key.
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        use_fake_llm=True,
        database_url=migrated_database,
        max_message_chars=200,
    )
    app = create_app(settings)
    # ASGITransport does not run lifespan, and the container is built there.
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

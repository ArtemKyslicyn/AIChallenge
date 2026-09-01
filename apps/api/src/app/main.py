from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.api.errors import register_error_handlers
from app.adapters.api.health import router as health_router
from app.adapters.api.llm import router as llm_router
from app.adapters.api.sessions import router as sessions_router
from app.core.deps import SESSION_TOKEN_HEADER, VISITOR_ID_HEADER, build_container
from app.core.logging import configure_logging
from app.core.settings import Settings, get_settings

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = build_container(app.state.settings)
    app.state.container = container
    try:
        yield
    finally:
        await container.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="AIChallenge API", lifespan=lifespan)
    app.state.settings = settings

    # Only needed when the browser talks to the API on another origin, i.e.
    # local Vite dev. Behind the nginx proxy the list stays empty.
    origins = settings.cors_origins_list()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", SESSION_TOKEN_HEADER, VISITOR_ID_HEADER],
        )

    for router in (health_router, sessions_router, llm_router):
        app.include_router(router, prefix=API_PREFIX)

    register_error_handlers(app)
    return app


app = create_app()

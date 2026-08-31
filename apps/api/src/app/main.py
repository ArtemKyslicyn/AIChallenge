from fastapi import FastAPI

from app.adapters.api.health import router as health_router
from app.core.logging import configure_logging

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="AIChallenge API")
    app.include_router(health_router, prefix=API_PREFIX)
    return app


app = create_app()

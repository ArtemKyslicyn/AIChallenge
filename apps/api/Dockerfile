# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies resolve in their own layer, so source edits do not re-resolve.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev


FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MEDIA_DIR=/app/data/media

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/media \
    && chown -R appuser:appuser /app/data

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app /app
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Entrypoint starts as root only long enough to chown the media volume, then
# drops to appuser (see docker-entrypoint.sh).
USER root
EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
# Migrations are the single source of schema truth, so they run before serving.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]

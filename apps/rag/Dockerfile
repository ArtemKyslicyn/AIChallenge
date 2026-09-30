# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml ./
# Lock generated at build when missing — prefer checked-in uv.lock when present.
COPY uv.lock* ./
RUN if [ -f uv.lock ]; then uv sync --frozen --no-dev --no-install-project; \
    else uv sync --no-dev --no-install-project; fi
COPY src ./src
RUN if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi

FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RAG_HOST=0.0.0.0 \
    RAG_PORT=18766 \
    RAG_DATA_DIR=/app/data \
    RAG_CORPUS_DIR=/app/corpus \
    EMBEDDING_PROVIDER=api

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app /app
RUN mkdir -p /app/data /app/corpus && chown appuser:appuser /app/data /app/corpus
USER appuser
EXPOSE 18766
HEALTHCHECK --interval=10s --timeout=3s --retries=5 --start-period=25s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:18766/health').status==200 else 1)"
CMD ["python", "-m", "aichallenge_rag"]

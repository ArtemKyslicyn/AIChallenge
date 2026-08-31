"""One JSON error shape for the whole API. No secrets, no stack traces."""

from __future__ import annotations

import logging
import re

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.domain.errors import (
    DomainError,
    LLMExhaustedError,
    LLMProviderError,
    LLMStreamAbortedError,
    MessageNotFoundError,
    MessageValidationError,
    ProbeDisabledError,
    ScenarioNotFoundError,
    SessionClosedError,
    SessionNotFoundError,
)

logger = logging.getLogger(__name__)

_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    SessionNotFoundError: status.HTTP_404_NOT_FOUND,
    MessageNotFoundError: status.HTTP_404_NOT_FOUND,
    ScenarioNotFoundError: status.HTTP_404_NOT_FOUND,
    ProbeDisabledError: status.HTTP_404_NOT_FOUND,
    SessionClosedError: status.HTTP_409_CONFLICT,
    MessageValidationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    LLMExhaustedError: status.HTTP_503_SERVICE_UNAVAILABLE,
    LLMStreamAbortedError: status.HTTP_502_BAD_GATEWAY,
    LLMProviderError: status.HTTP_502_BAD_GATEWAY,
}


def _code(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name.removesuffix("Error")).lower()


def _status_for(exc: DomainError) -> int:
    for klass in type(exc).__mro__:
        if klass in _STATUS_BY_ERROR:
            return _STATUS_BY_ERROR[klass]
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def _body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DomainError)
        code = _status_for(exc)
        if code >= 500:
            logger.warning("domain error path=%s code=%s", request.url.path, code)
        return JSONResponse(status_code=code, content=_body(_code(type(exc).__name__), str(exc)))

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, HTTPException)
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(f"http_{exc.status_code}", str(exc.detail)),
            headers=exc.headers,
        )

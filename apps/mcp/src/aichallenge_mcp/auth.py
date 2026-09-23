"""Bearer token for the HTTP transport. Stdio stays local-process only."""

from __future__ import annotations

import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        if request.url.path in {"/health", "/"}:
            return await call_next(request)
        token = os.environ.get("MCP_SHARED_TOKEN", "")
        if not token:
            return JSONResponse({"error": "MCP_SHARED_TOKEN unset"}, status_code=503)
        auth = request.headers.get("authorization", "")
        expected = f"Bearer {token}"
        if not hmac.compare_digest(auth, expected):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

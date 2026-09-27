"""Session guest MCP routes — mounted on the sessions router."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.application.guest_mcp import (
    GuestMcpAuthError,
    GuestMcpUnreachableError,
    connect_guest_mcp,
    disconnect_guest_mcp,
    list_guest_mcp,
    set_guest_enabled,
)
from app.core.deps import AuthorizedSession, get_container, resolve_visitor_identity, visitor_id_header
from app.domain.guest_mcp import GuestMcpServer, GuestMcpUrlError

router = APIRouter()

_CONNECT_TIMEOUT_DETAIL = "Сервер не ответил за 8 секунд."
_AUTH_DETAIL = "Неверный токен сервера."
_UNREACHABLE_DETAIL = "Не удалось подключиться к серверу."


class GuestMcpConnectRequest(BaseModel):
    name: str = ""
    url: str
    token: str = ""


class GuestMcpPatchRequest(BaseModel):
    enabled: bool


class GuestMcpServerResponse(BaseModel):
    id: UUID
    name: str
    url: str
    enabled: bool
    tool_names: list[str]
    status: str
    safe_error: str | None = None


class GuestMcpListResponse(BaseModel):
    servers: list[GuestMcpServerResponse]


def _server_response(server: GuestMcpServer) -> GuestMcpServerResponse:
    return GuestMcpServerResponse(
        id=server.id,
        name=server.name,
        url=server.url,
        enabled=server.enabled,
        tool_names=list(server.tool_names),
        status=server.status,
        safe_error=server.safe_error,
    )


def _distinct_id(request: Request, client_visitor_id: str | None) -> str:
    identity = resolve_visitor_identity(request, client_visitor_id)
    if identity is not None:
        return identity[0]
    return "anonymous"


def _raise_connect_error(exc: BaseException) -> None:
    if isinstance(exc, GuestMcpUrlError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    if isinstance(exc, GuestMcpAuthError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=_AUTH_DETAIL) from exc
    if isinstance(exc, TimeoutError):
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, detail=_CONNECT_TIMEOUT_DETAIL) from exc
    if isinstance(exc, GuestMcpUnreachableError):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=_UNREACHABLE_DETAIL) from exc
    raise exc


@router.get("/{session_id}/guest-mcp", response_model=GuestMcpListResponse)
async def list_guest_mcp_servers(
    request: Request,
    session: AuthorizedSession,
) -> GuestMcpListResponse:
    container = get_container(request)
    servers = await list_guest_mcp(session.id, container.guest_mcp_registry)
    return GuestMcpListResponse(servers=[_server_response(s) for s in servers])


@router.post("/{session_id}/guest-mcp", response_model=GuestMcpServerResponse)
async def connect_guest_mcp_server(
    payload: GuestMcpConnectRequest,
    request: Request,
    session: AuthorizedSession,
    client_visitor_id: Annotated[str | None, Depends(visitor_id_header)] = None,
) -> GuestMcpServerResponse:
    container = get_container(request)
    try:
        server = await connect_guest_mcp(
            session.id,
            payload.name,
            payload.url,
            payload.token,
            client=container.guest_mcp_client,
            registry=container.guest_mcp_registry,
            analytics=container.analytics,
            distinct_id=_distinct_id(request, client_visitor_id),
            allow_loopback=container.settings.guest_mcp_allow_loopback,
        )
    except (GuestMcpUrlError, GuestMcpAuthError, TimeoutError, GuestMcpUnreachableError) as exc:
        _raise_connect_error(exc)
    return _server_response(server)


@router.patch("/{session_id}/guest-mcp/{server_id}", response_model=GuestMcpServerResponse)
async def patch_guest_mcp_server(
    server_id: UUID,
    payload: GuestMcpPatchRequest,
    request: Request,
    session: AuthorizedSession,
    client_visitor_id: Annotated[str | None, Depends(visitor_id_header)] = None,
) -> GuestMcpServerResponse:
    container = get_container(request)
    try:
        server = await set_guest_enabled(
            session.id,
            server_id,
            payload.enabled,
            registry=container.guest_mcp_registry,
            analytics=container.analytics,
            distinct_id=_distinct_id(request, client_visitor_id),
        )
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Сервер не найден.") from None
    return _server_response(server)


@router.delete("/{session_id}/guest-mcp/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_guest_mcp_server(
    server_id: UUID,
    request: Request,
    session: AuthorizedSession,
    client_visitor_id: Annotated[str | None, Depends(visitor_id_header)] = None,
) -> None:
    container = get_container(request)
    try:
        await disconnect_guest_mcp(
            session.id,
            server_id,
            registry=container.guest_mcp_registry,
            analytics=container.analytics,
            distinct_id=_distinct_id(request, client_visitor_id),
        )
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Сервер не найден.") from None

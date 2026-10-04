"""Stand RAG proxy: stats, upload, admin settings."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.adapters.api.auth import OptionalAuthUser, require_auth_user
from app.core.deps import AuthorizedSession, get_container
from app.domain.auth import UserAccount
from app.domain.guest_mcp import GuestMcpForbiddenError, assert_guest_mcp_email_allowed

router = APIRouter(tags=["rag"])


class RagSettingsPatch(BaseModel):
    local_embeddings: bool | None = None
    chunk_strategy: str | None = Field(default=None, pattern="^(fixed|structural)$")


def _admin_emails(container: Any) -> str:
    admin = str(container.settings.rag_admin_emails or "").strip()
    if admin:
        return admin
    return str(container.settings.guest_mcp_allowed_emails or "").strip()


def _rag_owner_id(auth_user: UserAccount | None, session: Any) -> str:
    if auth_user is not None:
        return str(auth_user.id)
    return str(getattr(session, "visitor_hash", None) or "")


@router.get("/rag/stats")
async def rag_stats(request: Request) -> dict[str, Any]:
    container = get_container(request)
    try:
        return await container.rag_client.stats()
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="База знаний недоступна.") from exc


@router.get("/sessions/{session_id}/rag/documents")
async def list_session_rag_documents(
    session_id: UUID,
    request: Request,
    session: AuthorizedSession,
    auth_user: OptionalAuthUser,
) -> dict[str, Any]:
    """List documents uploaded by this visitor/user (session scope only)."""
    if session.id != session_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Сессия не найдена.")
    container = get_container(request)
    owner = _rag_owner_id(auth_user, session)
    if not owner:
        return {"documents": [], "count": 0}
    try:
        return await container.rag_client.list_documents(owner_id=owner, all_owners=False)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Не удалось получить список документов."
        ) from exc


@router.delete("/sessions/{session_id}/rag/documents")
async def delete_session_rag_document(
    session_id: UUID,
    request: Request,
    session: AuthorizedSession,
    auth_user: OptionalAuthUser,
    source: str,
) -> dict[str, Any]:
    """Delete one of this visitor/user's session-scoped documents."""
    if session.id != session_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Сессия не найдена.")
    container = get_container(request)
    owner = _rag_owner_id(auth_user, session)
    if not owner or not source.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Нужен source.")
    try:
        return await container.rag_client.delete_document(
            source=source.strip(),
            scope="session",
            owner_id=owner,
        )
    except Exception as exc:
        detail = "Не удалось удалить документ."
        status_code = status.HTTP_502_BAD_GATEWAY
        resp = getattr(exc, "response", None)
        if resp is not None and getattr(resp, "status_code", None) == 404:
            status_code = status.HTTP_404_NOT_FOUND
            detail = "Документ не найден."
        raise HTTPException(status_code, detail=detail) from exc


@router.get("/rag/documents")
async def list_all_rag_documents(
    request: Request,
    user: Annotated[UserAccount, Depends(require_auth_user)],
) -> dict[str, Any]:
    """Admin: all stand + session documents."""
    container = get_container(request)
    try:
        assert_guest_mcp_email_allowed(user.email, _admin_emails(container))
    except GuestMcpForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=exc.message) from exc
    try:
        return await container.rag_client.list_documents(all_owners=True)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Не удалось получить список документов."
        ) from exc


@router.delete("/rag/documents")
async def delete_any_rag_document(
    request: Request,
    user: Annotated[UserAccount, Depends(require_auth_user)],
    source: str,
    scope: str = "session",
    owner_id: str = "",
) -> dict[str, Any]:
    """Admin: delete any document (session or stand)."""
    container = get_container(request)
    try:
        assert_guest_mcp_email_allowed(user.email, _admin_emails(container))
    except GuestMcpForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=exc.message) from exc
    if not source.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Нужен source.")
    try:
        return await container.rag_client.delete_document(
            source=source.strip(),
            scope=(scope or "session").strip(),
            owner_id=owner_id,
        )
    except Exception as exc:
        detail = "Не удалось удалить документ."
        status_code = status.HTTP_502_BAD_GATEWAY
        resp = getattr(exc, "response", None)
        if resp is not None and getattr(resp, "status_code", None) == 404:
            status_code = status.HTTP_404_NOT_FOUND
            detail = "Документ не найден."
        raise HTTPException(status_code, detail=detail) from exc


@router.post("/sessions/{session_id}/rag/documents")
async def upload_rag_document(
    session_id: UUID,
    request: Request,
    session: AuthorizedSession,
    auth_user: OptionalAuthUser,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    if session.id != session_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Сессия не найдена.")
    container = get_container(request)
    raw = await file.read()
    if not raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Пустой файл.")
    if len(raw) > 5_000_000:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Файл слишком большой."
        )
    name = file.filename or "upload.txt"
    owner = _rag_owner_id(auth_user, session)
    try:
        result = await container.rag_client.add_document_bytes(
            filename=name,
            data=raw,
            scope="session",
            owner_id=owner,
        )
        # Ensure clients always see filename even if sidecar omits it.
        if not result.get("filename"):
            result["filename"] = name
        return result
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Не удалось добавить документ в базу."
        ) from exc


@router.post("/rag/index")
async def rag_reindex(
    request: Request,
    user: Annotated[UserAccount, Depends(require_auth_user)],
    strategy: str | None = None,
) -> dict[str, Any]:
    container = get_container(request)
    try:
        assert_guest_mcp_email_allowed(user.email, _admin_emails(container))
    except GuestMcpForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=exc.message) from exc
    try:
        return await container.rag_client.reindex(strategy=strategy)
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Индексация не удалась.") from exc


@router.post("/rag/heal")
async def rag_heal(
    request: Request,
    user: Annotated[UserAccount, Depends(require_auth_user)],
) -> dict[str, Any]:
    """Rebuild embeddings when chunks exist without a vector matrix."""
    container = get_container(request)
    try:
        assert_guest_mcp_email_allowed(user.email, _admin_emails(container))
    except GuestMcpForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=exc.message) from exc
    try:
        return dict(await container.rag_client.heal())
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Heal не удался.") from exc


@router.patch("/rag/settings")
async def rag_settings_patch(
    payload: RagSettingsPatch,
    request: Request,
    user: Annotated[UserAccount, Depends(require_auth_user)],
) -> dict[str, Any]:
    container = get_container(request)
    try:
        assert_guest_mcp_email_allowed(user.email, _admin_emails(container))
    except GuestMcpForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=exc.message) from exc
    body: dict[str, object] = {}
    if payload.local_embeddings is not None:
        body["local_embeddings"] = payload.local_embeddings
    if payload.chunk_strategy is not None:
        body["chunk_strategy"] = payload.chunk_strategy
    try:
        return await container.rag_client.patch_settings(body)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Не удалось обновить настройки базы."
        ) from exc


@router.get("/rag/admin-eligible")
async def rag_admin_eligible(
    request: Request,
    user: Annotated[UserAccount, Depends(require_auth_user)],
) -> dict[str, bool]:
    container = get_container(request)
    try:
        assert_guest_mcp_email_allowed(user.email, _admin_emails(container))
        return {"eligible": True}
    except GuestMcpForbiddenError:
        return {"eligible": False}

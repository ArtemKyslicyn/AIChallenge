"""Profile endpoints for one Ollama origin. The key is write-only."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.adapters.api.auth import RequiredAuthUser
from app.adapters.llm.ollama_native import fetch_ollama_tags
from app.adapters.persistence.local_llm_repo import SqlAlchemyLocalLlmSourceRepository
from app.application.local_llm import (
    connect_local_llm,
    disconnect_local_llm,
    to_public,
    validate_stored_origin,
)
from app.core.deps import DbSession, close_quietly, get_container
from app.domain.auth import UserAccount
from app.domain.errors import LLMProviderError
from app.domain.local_llm import (
    FORBIDDEN_MESSAGE,
    LocalLlmForbiddenError,
    LocalLlmSource,
    LocalLlmUrlError,
    assert_local_llm_email_allowed,
)

router = APIRouter(prefix="/me", tags=["local-llm"])


class LocalLlmConnectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=300)
    api_key: str | None = None


class LocalLlmSourceResponse(BaseModel):
    name: str
    base_host: str
    status: str
    models: list[str]
    enabled: bool


def _dto(source: LocalLlmSource) -> LocalLlmSourceResponse:
    public = to_public(source)
    return LocalLlmSourceResponse(
        name=public.name,
        base_host=public.base_host,
        status=public.status,
        models=list(public.models),
        enabled=public.enabled,
    )


def _assert_local_llm_access(request: Request, user_email: str) -> None:
    container = get_container(request)
    try:
        assert_local_llm_email_allowed(
            user_email,
            container.settings.dangerous_admin_emails(),
        )
    except LocalLlmForbiddenError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=FORBIDDEN_MESSAGE,
        ) from exc


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LocalLlmForbiddenError):
        return HTTPException(status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_MESSAGE)
    if isinstance(exc, LocalLlmUrlError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.message)
    if isinstance(exc, LLMProviderError):
        code = (
            status.HTTP_504_GATEWAY_TIMEOUT
            if exc.kind == "timeout"
            else status.HTTP_502_BAD_GATEWAY
        )
        return HTTPException(code, detail=str(exc))
    raise exc


async def load_user_source(request: Request, user: UserAccount | None) -> LocalLlmSource | None:
    """Load a connected origin only when the caller may use local LLM and policy still allows it."""
    if user is None:
        return None
    container = get_container(request)
    try:
        assert_local_llm_email_allowed(
            user.email,
            container.settings.dangerous_admin_emails(),
        )
    except LocalLlmForbiddenError:
        return None
    db = container.sessionmaker()
    try:
        source = await SqlAlchemyLocalLlmSourceRepository(db).get_for_user(user.id)
    finally:
        await close_quietly(db)
    if source is None:
        return None
    return validate_stored_origin(source, container.settings)


@router.get("/llm-sources", response_model=LocalLlmSourceResponse | None)
async def get_local_llm_source(
    request: Request, user: RequiredAuthUser, db: DbSession
) -> LocalLlmSourceResponse | None:
    _assert_local_llm_access(request, user.email)
    source = await SqlAlchemyLocalLlmSourceRepository(db).get_for_user(user.id)
    if source is None:
        return None
    allowed = validate_stored_origin(source, get_container(request).settings)
    if allowed is None:
        return None
    return _dto(allowed)


@router.put("/llm-sources", response_model=LocalLlmSourceResponse)
async def put_local_llm_source(
    payload: LocalLlmConnectRequest,
    request: Request,
    user: RequiredAuthUser,
    db: DbSession,
) -> LocalLlmSourceResponse:
    _assert_local_llm_access(request, user.email)
    container = get_container(request)
    repo = SqlAlchemyLocalLlmSourceRepository(db)
    try:
        public = await connect_local_llm(
            user.id,
            name=payload.name,
            base_url=payload.base_url,
            api_key=payload.api_key,
            settings=container.settings,
            repo=repo,
            tags=fetch_ollama_tags,
        )
    except (LocalLlmUrlError, LLMProviderError, LocalLlmForbiddenError) as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return LocalLlmSourceResponse(
        name=public.name,
        base_host=public.base_host,
        status=public.status,
        models=list(public.models),
        enabled=public.enabled,
    )


@router.delete("/llm-sources", status_code=status.HTTP_204_NO_CONTENT)
async def delete_local_llm_source(
    request: Request, user: RequiredAuthUser, db: DbSession
) -> None:
    _assert_local_llm_access(request, user.email)
    await disconnect_local_llm(user.id, SqlAlchemyLocalLlmSourceRepository(db))
    await db.commit()


def source_model_ids(source: LocalLlmSource | None) -> list[str]:
    from app.domain.local_llm import canonical_model_id

    if source is None or not source.enabled or source.status != "connected":
        return []
    ids: list[str] = []
    for tag in source.models:
        try:
            ids.append(canonical_model_id(tag))
        except LocalLlmUrlError:
            continue
    return ids

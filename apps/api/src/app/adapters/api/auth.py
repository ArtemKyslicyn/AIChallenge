"""Day 12 — email/password auth API (anonymous mode remains default)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.adapters.persistence.user_repo import (
    SqlAlchemyAuthTokenRepository,
    SqlAlchemyUserRepository,
)
from app.application.auth import login_user, register_user
from app.core.deps import ClientVisitorId, DbSession
from app.domain.auth import UserAccount
from app.domain.errors import MessageValidationError
from app.domain.owner_key import memory_owner_key

router = APIRouter(prefix="/auth", tags=["auth"])

AUTH_TOKEN_HEADER = "X-Auth-Token"


class AuthCredentialsRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=120)


class UserMeResponse(BaseModel):
    id: str
    email: str
    display_name: str
    owner_key: str
    anonymous: bool = False


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserMeResponse


def _user_dto(user: UserAccount, *, visitor_id: str = "") -> UserMeResponse:
    return UserMeResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        owner_key=memory_owner_key(visitor_id=visitor_id, user_id=user.id),
        anonymous=False,
    )


async def optional_auth_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    x_auth_token: Annotated[str | None, Header(alias=AUTH_TOKEN_HEADER)] = None,
) -> UserAccount | None:
    token = (x_auth_token or "").strip()
    if not token and authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
    if not token:
        return None
    user_id = await SqlAlchemyAuthTokenRepository(db).find_user_id(token)
    if user_id is None:
        return None
    return await SqlAlchemyUserRepository(db).get(user_id)


async def require_auth_user(
    user: Annotated[UserAccount | None, Depends(optional_auth_user)],
) -> UserAccount:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Требуется вход.")
    return user


OptionalAuthUser = Annotated[UserAccount | None, Depends(optional_auth_user)]
RequiredAuthUser = Annotated[UserAccount, Depends(require_auth_user)]


@router.post("/register", response_model=AuthTokenResponse)
async def register(
    payload: AuthCredentialsRequest,
    db: DbSession,
    client_visitor_id: ClientVisitorId,
) -> AuthTokenResponse:
    try:
        user, token = await register_user(
            db,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            visitor_id=client_visitor_id,
        )
    except ValueError as exc:
        raise MessageValidationError(str(exc)) from exc
    await db.commit()
    return AuthTokenResponse(
        access_token=token,
        user=_user_dto(user, visitor_id=client_visitor_id),
    )


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    payload: AuthCredentialsRequest,
    db: DbSession,
    client_visitor_id: ClientVisitorId,
) -> AuthTokenResponse:
    try:
        user, token = await login_user(
            db,
            email=payload.email,
            password=payload.password,
            visitor_id=client_visitor_id,
        )
    except ValueError as exc:
        raise MessageValidationError(str(exc)) from exc
    await db.commit()
    return AuthTokenResponse(
        access_token=token,
        user=_user_dto(user, visitor_id=client_visitor_id),
    )


@router.post("/logout")
async def logout(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    x_auth_token: Annotated[str | None, Header(alias=AUTH_TOKEN_HEADER)] = None,
) -> dict[str, bool]:
    token = (x_auth_token or "").strip()
    if not token and authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
    if token:
        await SqlAlchemyAuthTokenRepository(db).revoke_token(token)
        await db.commit()
    return {"ok": True}


@router.get("/me", response_model=UserMeResponse)
async def me(
    db: DbSession,
    client_visitor_id: ClientVisitorId,
    user: OptionalAuthUser,
) -> UserMeResponse:
    if user is None:
        return UserMeResponse(
            id="",
            email="",
            display_name="",
            owner_key=memory_owner_key(visitor_id=client_visitor_id, user_id=None),
            anonymous=True,
        )
    return _user_dto(user, visitor_id=client_visitor_id)

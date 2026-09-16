"""Day 12 — preference profiles + expert lenses API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.adapters.api.auth import OptionalAuthUser
from app.adapters.persistence.preference_repo import SqlAlchemyPreferenceProfileRepository
from app.application.auth import ensure_demo_preference_profiles
from app.core.deps import ClientVisitorId, DbSession
from app.domain.errors import MessageValidationError
from app.domain.owner_key import memory_owner_key
from app.domain.personalization import EXPERT_LENSES, PreferenceProfile

router = APIRouter(prefix="/personalization", tags=["personalization"])


class PreferenceProfilePayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    style: str = Field(default="", max_length=2000)
    format: str = Field(default="", max_length=2000)
    constraints: str = Field(default="", max_length=2000)
    activate: bool = False


class PreferenceProfileResponse(BaseModel):
    id: str
    name: str
    style: str
    format: str
    constraints: str
    is_active: bool


class ExpertLensResponse(BaseModel):
    id: str
    label: str
    system_addendum: str


def _owner(visitor_id: str, user: OptionalAuthUser) -> str:
    return memory_owner_key(
        visitor_id=visitor_id,
        user_id=user.id if user is not None else None,
    )


def _pref_dto(p: PreferenceProfile) -> PreferenceProfileResponse:
    return PreferenceProfileResponse(
        id=str(p.id),
        name=p.name,
        style=p.style or "",
        format=p.format or "",
        constraints=p.constraints or "",
        is_active=bool(p.is_active),
    )


@router.get("/lenses", response_model=list[ExpertLensResponse])
async def list_lenses() -> list[ExpertLensResponse]:
    return [
        ExpertLensResponse(id=lens.id, label=lens.label, system_addendum=lens.system_addendum)
        for lens in EXPERT_LENSES
    ]


@router.get("/profiles", response_model=list[PreferenceProfileResponse])
async def list_profiles(
    db: DbSession,
    client_visitor_id: ClientVisitorId,
    user: OptionalAuthUser,
) -> list[PreferenceProfileResponse]:
    owner = _owner(client_visitor_id, user)
    await ensure_demo_preference_profiles(db, owner)
    await db.commit()
    rows = await SqlAlchemyPreferenceProfileRepository(db).list_for_owner(owner)
    return [_pref_dto(r) for r in rows]


@router.post("/profiles", response_model=PreferenceProfileResponse)
async def create_profile(
    payload: PreferenceProfilePayload,
    db: DbSession,
    client_visitor_id: ClientVisitorId,
    user: OptionalAuthUser,
) -> PreferenceProfileResponse:
    owner = _owner(client_visitor_id, user)
    try:
        created = await SqlAlchemyPreferenceProfileRepository(db).create(
            owner_key=owner,
            name=payload.name,
            style=payload.style,
            format=payload.format,
            constraints=payload.constraints,
            activate=payload.activate,
        )
    except Exception as exc:  # noqa: BLE001
        raise MessageValidationError(str(exc)) from exc
    await db.commit()
    return _pref_dto(created)


@router.patch("/profiles/{profile_id}", response_model=PreferenceProfileResponse)
async def update_profile(
    profile_id: UUID,
    payload: PreferenceProfilePayload,
    db: DbSession,
    client_visitor_id: ClientVisitorId,
    user: OptionalAuthUser,
) -> PreferenceProfileResponse:
    owner = _owner(client_visitor_id, user)
    repo = SqlAlchemyPreferenceProfileRepository(db)
    existing = await repo.get(profile_id)
    if existing is None or existing.owner_key != owner:
        raise HTTPException(status_code=404, detail="Профиль не найден.")
    existing.name = payload.name
    existing.style = payload.style
    existing.format = payload.format
    existing.constraints = payload.constraints
    saved = await repo.save(existing)
    if payload.activate:
        saved = await repo.activate(owner, profile_id)
    await db.commit()
    return _pref_dto(saved)


@router.post("/profiles/{profile_id}/activate", response_model=PreferenceProfileResponse)
async def activate_profile(
    profile_id: UUID,
    db: DbSession,
    client_visitor_id: ClientVisitorId,
    user: OptionalAuthUser,
) -> PreferenceProfileResponse:
    owner = _owner(client_visitor_id, user)
    try:
        active = await SqlAlchemyPreferenceProfileRepository(db).activate(owner, profile_id)
    except ValueError as exc:
        raise MessageValidationError(str(exc)) from exc
    await db.commit()
    return _pref_dto(active)


@router.delete("/profiles/{profile_id}")
async def delete_profile(
    profile_id: UUID,
    db: DbSession,
    client_visitor_id: ClientVisitorId,
    user: OptionalAuthUser,
) -> dict[str, bool]:
    owner = _owner(client_visitor_id, user)
    try:
        await SqlAlchemyPreferenceProfileRepository(db).delete(owner, profile_id)
    except ValueError as exc:
        raise MessageValidationError(str(exc)) from exc
    await db.commit()
    return {"ok": True}

"""Register / login + claim visitor-owned agent state onto user."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.long_term_memory_repo import SqlAlchemyLongTermMemoryRepository
from app.adapters.persistence.models import AgentDialogRow, AgentLongTermMemoryRow
from app.adapters.persistence.preference_repo import SqlAlchemyPreferenceProfileRepository
from app.adapters.persistence.user_repo import (
    SqlAlchemyAuthTokenRepository,
    SqlAlchemyUserRepository,
)
from app.domain.agent_memory import LongTermMemory
from app.domain.auth import (
    UserAccount,
    hash_password,
    mint_auth_token,
    validate_email,
    validate_password,
    verify_password,
)
from app.domain.errors import MessageValidationError
from app.domain.owner_key import memory_owner_key
from app.domain.personalization import DEMO_PREFERENCE_SEEDS


async def claim_visitor_to_user(
    db: AsyncSession,
    *,
    visitor_id: str,
    user_id: UUID,
) -> str:
    """Remap dialogs + LTM + prefs from visitor key → user:<uuid>; return new owner_key."""
    visitor = (visitor_id or "").strip().lower()
    user_key = memory_owner_key(visitor_id=visitor, user_id=user_id)
    if not visitor or visitor == user_key:
        return user_key

    await db.execute(
        update(AgentDialogRow)
        .where(AgentDialogRow.client_visitor_id == visitor)
        .values(client_visitor_id=user_key, updated_at=datetime.now(UTC))
    )

    ltm = SqlAlchemyLongTermMemoryRepository(db)
    visitor_mem = await ltm.get(visitor)
    user_mem = await ltm.get(user_key)
    merged_profile = {**(visitor_mem.profile or {}), **(user_mem.profile or {})}
    merged_knowledge = {**(visitor_mem.knowledge or {}), **(user_mem.knowledge or {})}
    decisions: list[str] = []
    for item in list(visitor_mem.decisions or []) + list(user_mem.decisions or []):
        if item and item not in decisions:
            decisions.append(item)

    await ltm.save(
        user_key,
        LongTermMemory(profile=merged_profile, decisions=decisions, knowledge=merged_knowledge),
    )
    visitor_row = await db.get(AgentLongTermMemoryRow, visitor)
    if visitor_row is not None:
        await db.delete(visitor_row)

    prefs = SqlAlchemyPreferenceProfileRepository(db)
    await prefs.rekey_owner(from_key=visitor, to_key=user_key)

    await db.flush()
    return user_key


async def ensure_demo_preference_profiles(db: AsyncSession, owner_key: str) -> None:
    repo = SqlAlchemyPreferenceProfileRepository(db)
    existing = await repo.list_for_owner(owner_key)
    if existing:
        return
    first_id = None
    for i, seed in enumerate(DEMO_PREFERENCE_SEEDS):
        created = await repo.create(
            owner_key=owner_key,
            name=seed["name"],
            style=seed["style"],
            format=seed["format"],
            constraints=seed["constraints"],
            activate=False,
        )
        if i == 0:
            first_id = created.id
    if first_id is not None:
        await repo.activate(owner_key, first_id)


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str = "",
    visitor_id: str | None = None,
) -> tuple[UserAccount, str]:
    email_n = validate_email(email)
    validate_password(password)
    users = SqlAlchemyUserRepository(db)
    if await users.get_by_email(email_n) is not None:
        raise MessageValidationError("Email уже зарегистрирован.")
    user = await users.create(
        email=email_n,
        password_hash=hash_password(password),
        display_name=display_name or email_n.split("@")[0],
    )
    token = mint_auth_token()
    await SqlAlchemyAuthTokenRepository(db).create(user_id=user.id, plaintext_token=token)
    if visitor_id:
        owner = await claim_visitor_to_user(db, visitor_id=visitor_id, user_id=user.id)
        await ensure_demo_preference_profiles(db, owner)
    else:
        await ensure_demo_preference_profiles(db, memory_owner_key(visitor_id="", user_id=user.id))
    return user, token


async def login_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    visitor_id: str | None = None,
) -> tuple[UserAccount, str]:
    email_n = validate_email(email)
    users = SqlAlchemyUserRepository(db)
    user = await users.get_by_email(email_n)
    if user is None or not verify_password(password, user.password_hash):
        raise MessageValidationError("Неверный email или пароль.")
    token = mint_auth_token()
    await SqlAlchemyAuthTokenRepository(db).create(user_id=user.id, plaintext_token=token)
    if visitor_id:
        owner = await claim_visitor_to_user(db, visitor_id=visitor_id, user_id=user.id)
        await ensure_demo_preference_profiles(db, owner)
    else:
        await ensure_demo_preference_profiles(db, memory_owner_key(visitor_id="", user_id=user.id))
    return user, token

"""SQLAlchemy users + auth tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import AuthTokenRow, UserRow
from app.domain.auth import UserAccount, hash_auth_token


class SqlAlchemyUserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _to_domain(self, row: UserRow) -> UserAccount:
        return UserAccount(
            id=row.id,
            email=row.email,
            password_hash=row.password_hash,
            display_name=row.display_name or "",
            created_at=row.created_at,
        )

    async def get(self, user_id: UUID) -> UserAccount | None:
        row = await self._db.get(UserRow, user_id)
        return self._to_domain(row) if row else None

    async def get_by_email(self, email: str) -> UserAccount | None:
        result = await self._db.execute(select(UserRow).where(UserRow.email == email))
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str = "",
    ) -> UserAccount:
        now = datetime.now(UTC)
        row = UserRow(
            id=uuid4(),
            email=email,
            password_hash=password_hash,
            display_name=(display_name or "").strip()[:120],
            created_at=now,
        )
        self._db.add(row)
        await self._db.flush()
        return self._to_domain(row)


class SqlAlchemyAuthTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        user_id: UUID,
        plaintext_token: str,
        ttl_days: int = 30,
    ) -> None:
        now = datetime.now(UTC)
        row = AuthTokenRow(
            id=uuid4(),
            user_id=user_id,
            token_hash=hash_auth_token(plaintext_token),
            created_at=now,
            expires_at=now + timedelta(days=ttl_days),
        )
        self._db.add(row)
        await self._db.flush()

    async def find_user_id(self, plaintext_token: str) -> UUID | None:
        digest = hash_auth_token(plaintext_token)
        result = await self._db.execute(
            select(AuthTokenRow).where(AuthTokenRow.token_hash == digest)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        if row.expires_at is not None and row.expires_at < datetime.now(UTC):
            return None
        return row.user_id

    async def revoke_token(self, plaintext_token: str) -> None:
        digest = hash_auth_token(plaintext_token)
        await self._db.execute(delete(AuthTokenRow).where(AuthTokenRow.token_hash == digest))
        await self._db.flush()

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        await self._db.execute(delete(AuthTokenRow).where(AuthTokenRow.user_id == user_id))
        await self._db.flush()

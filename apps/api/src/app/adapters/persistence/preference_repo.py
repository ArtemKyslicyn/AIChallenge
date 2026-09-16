"""Preference profile persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import AgentPreferenceProfileRow
from app.domain.personalization import PreferenceProfile


class SqlAlchemyPreferenceProfileRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _to_domain(self, row: AgentPreferenceProfileRow) -> PreferenceProfile:
        return PreferenceProfile(
            id=row.id,
            owner_key=row.owner_key,
            name=row.name,
            style=row.style or "",
            format=row.format or "",
            constraints=row.constraints or "",
            is_active=bool(row.is_active),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def list_for_owner(self, owner_key: str) -> list[PreferenceProfile]:
        result = await self._db.execute(
            select(AgentPreferenceProfileRow)
            .where(AgentPreferenceProfileRow.owner_key == owner_key)
            .order_by(AgentPreferenceProfileRow.created_at)
        )
        return [self._to_domain(r) for r in result.scalars().all()]

    async def get(self, profile_id: UUID) -> PreferenceProfile | None:
        row = await self._db.get(AgentPreferenceProfileRow, profile_id)
        return self._to_domain(row) if row else None

    async def get_active(self, owner_key: str) -> PreferenceProfile | None:
        result = await self._db.execute(
            select(AgentPreferenceProfileRow).where(
                AgentPreferenceProfileRow.owner_key == owner_key,
                AgentPreferenceProfileRow.is_active.is_(True),
            )
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def save(self, profile: PreferenceProfile) -> PreferenceProfile:
        now = datetime.now(UTC)
        row = await self._db.get(AgentPreferenceProfileRow, profile.id)
        if row is None:
            row = AgentPreferenceProfileRow(
                id=profile.id,
                owner_key=profile.owner_key,
                name=profile.name.strip()[:80] or "Профиль",
                style=(profile.style or "")[:2000],
                format=(profile.format or "")[:2000],
                constraints=(profile.constraints or "")[:2000],
                is_active=bool(profile.is_active),
                created_at=profile.created_at or now,
                updated_at=now,
            )
            self._db.add(row)
        else:
            row.name = profile.name.strip()[:80] or row.name
            row.style = (profile.style or "")[:2000]
            row.format = (profile.format or "")[:2000]
            row.constraints = (profile.constraints or "")[:2000]
            row.is_active = bool(profile.is_active)
            row.updated_at = now
        await self._db.flush()
        return self._to_domain(row)

    async def create(
        self,
        *,
        owner_key: str,
        name: str,
        style: str = "",
        format: str = "",
        constraints: str = "",
        activate: bool = False,
    ) -> PreferenceProfile:
        profile = PreferenceProfile(
            id=uuid4(),
            owner_key=owner_key,
            name=name,
            style=style,
            format=format,
            constraints=constraints,
            is_active=False,
        )
        saved = await self.save(profile)
        if activate:
            return await self.activate(owner_key, saved.id)
        return saved

    async def activate(self, owner_key: str, profile_id: UUID) -> PreferenceProfile:
        await self._db.execute(
            update(AgentPreferenceProfileRow)
            .where(AgentPreferenceProfileRow.owner_key == owner_key)
            .values(is_active=False)
        )
        row = await self._db.get(AgentPreferenceProfileRow, profile_id)
        if row is None or row.owner_key != owner_key:
            raise ValueError("Профиль не найден.")
        row.is_active = True
        row.updated_at = datetime.now(UTC)
        await self._db.flush()
        return self._to_domain(row)

    async def delete(self, owner_key: str, profile_id: UUID) -> None:
        row = await self._db.get(AgentPreferenceProfileRow, profile_id)
        if row is None or row.owner_key != owner_key:
            raise ValueError("Профиль не найден.")
        await self._db.delete(row)
        await self._db.flush()

    async def rekey_owner(self, *, from_key: str, to_key: str) -> None:
        """Move profiles from visitor key to user key (claim)."""
        if from_key == to_key:
            return
        existing = await self.list_for_owner(to_key)
        existing_names = {p.name for p in existing}
        for profile in await self.list_for_owner(from_key):
            row = await self._db.get(AgentPreferenceProfileRow, profile.id)
            if row is None:
                continue
            if row.name in existing_names:
                await self._db.delete(row)
            else:
                row.owner_key = to_key
                row.is_active = False
                row.updated_at = datetime.now(UTC)
        await self._db.flush()

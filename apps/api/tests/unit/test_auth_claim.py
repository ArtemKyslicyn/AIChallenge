"""Unit tests for Day-12 visitor→user claim merge."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from app.application.auth import claim_visitor_to_user, ensure_demo_preference_profiles
from app.domain.agent_memory import LongTermMemory
from app.domain.owner_key import memory_owner_key
from app.domain.personalization import PreferenceProfile


@dataclass
class FakeLTM:
    store: dict[str, LongTermMemory] = field(default_factory=dict)

    async def get(self, client_visitor_id: str) -> LongTermMemory:
        return self.store.get(client_visitor_id, LongTermMemory())

    async def save(self, client_visitor_id: str, memory: LongTermMemory) -> LongTermMemory:
        self.store[client_visitor_id] = memory
        return memory

    async def delete(self, client_visitor_id: str) -> None:
        self.store.pop(client_visitor_id, None)


@dataclass
class FakeDialogs:
    keys: list[str] = field(default_factory=list)

    async def rekey_client_visitor(self, *, from_key: str, to_key: str) -> None:
        self.keys = [to_key if k == from_key else k for k in self.keys]


@dataclass
class FakePrefs:
    rows: list[PreferenceProfile] = field(default_factory=list)

    async def list_for_owner(self, owner_key: str) -> list[PreferenceProfile]:
        return [p for p in self.rows if p.owner_key == owner_key]

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
        p = PreferenceProfile(
            id=uuid4(),
            owner_key=owner_key,
            name=name,
            style=style,
            format=format,
            constraints=constraints,
            is_active=activate,
        )
        self.rows.append(p)
        if activate:
            return await self.activate(owner_key, p.id)
        return p

    async def activate(self, owner_key: str, profile_id: UUID) -> PreferenceProfile:
        for p in self.rows:
            if p.owner_key == owner_key:
                p.is_active = p.id == profile_id
        for p in self.rows:
            if p.id == profile_id:
                return p
        raise ValueError("missing")

    async def rekey_owner(self, *, from_key: str, to_key: str) -> None:
        for p in self.rows:
            if p.owner_key == from_key:
                p.owner_key = to_key
                p.is_active = False


@pytest.mark.asyncio
async def test_claim_merges_ltm_and_rekeys() -> None:
    visitor = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    user_id = uuid4()
    user_key = memory_owner_key(visitor_id=visitor, user_id=user_id)
    ltm = FakeLTM(
        store={
            visitor: LongTermMemory(
                profile={"name": "Ada"},
                decisions=["d1"],
                knowledge={"k": "1"},
            ),
            user_key: LongTermMemory(
                profile={"city": "SPB"},
                decisions=["d2"],
                knowledge={"k": "2"},
            ),
        }
    )
    dialogs = FakeDialogs(keys=[visitor, visitor])
    prefs = FakePrefs(
        rows=[
            PreferenceProfile(id=uuid4(), owner_key=visitor, name="Кратко · JSON", is_active=True),
        ]
    )
    got = await claim_visitor_to_user(
        visitor_id=visitor,
        user_id=user_id,
        dialogs=dialogs,  # type: ignore[arg-type]
        long_term=ltm,  # type: ignore[arg-type]
        preferences=prefs,  # type: ignore[arg-type]
    )
    assert got == user_key
    assert visitor not in ltm.store
    merged = ltm.store[user_key]
    assert merged.profile == {"name": "Ada", "city": "SPB"}
    assert merged.knowledge["k"] == "2"
    assert merged.decisions == ["d1", "d2"]
    assert dialogs.keys == [user_key, user_key]
    assert all(p.owner_key == user_key for p in prefs.rows)


@pytest.mark.asyncio
async def test_ensure_demo_seeds_once() -> None:
    prefs = FakePrefs()
    await ensure_demo_preference_profiles(prefs, "owner-a")  # type: ignore[arg-type]
    await ensure_demo_preference_profiles(prefs, "owner-a")  # type: ignore[arg-type]
    assert len(prefs.rows) == 2
    assert sum(1 for p in prefs.rows if p.is_active) == 1

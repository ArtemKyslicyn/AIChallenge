"""Profile auth: patch display_name + change password."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.auth import change_password, update_display_name
from app.domain.auth import UserAccount, hash_password, verify_password
from app.domain.errors import MessageValidationError


class _MemUsers:
    def __init__(self, user: UserAccount) -> None:
        self.user = user

    async def get(self, user_id: UUID) -> UserAccount | None:
        return self.user if self.user.id == user_id else None

    async def get_by_email(self, email: str) -> UserAccount | None:
        return self.user if self.user.email == email else None

    async def create(self, **kwargs: object) -> UserAccount:
        raise AssertionError("unused")

    async def update_display_name(self, user_id: UUID, display_name: str) -> UserAccount:
        assert self.user.id == user_id
        self.user = UserAccount(
            id=self.user.id,
            email=self.user.email,
            password_hash=self.user.password_hash,
            display_name=display_name,
            created_at=self.user.created_at,
        )
        return self.user

    async def update_password_hash(self, user_id: UUID, password_hash: str) -> UserAccount:
        assert self.user.id == user_id
        self.user = UserAccount(
            id=self.user.id,
            email=self.user.email,
            password_hash=password_hash,
            display_name=self.user.display_name,
            created_at=self.user.created_at,
        )
        return self.user


class _MemTokens:
    def __init__(self) -> None:
        self.revoked: list[str] = []
        self.created: list[tuple[UUID, str]] = []

    async def create(self, *, user_id: UUID, plaintext_token: str, ttl_days: int = 30) -> None:
        del ttl_days
        self.created.append((user_id, plaintext_token))

    async def find_user_id(self, plaintext_token: str) -> UUID | None:
        del plaintext_token
        return None

    async def revoke_token(self, plaintext_token: str) -> None:
        self.revoked.append(plaintext_token)


def _user(password: str = "old-secret-99") -> UserAccount:
    return UserAccount(
        id=uuid4(),
        email="admin@example.com",
        password_hash=hash_password(password),
        display_name="Admin",
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_update_display_name_trims() -> None:
    users = _MemUsers(_user())
    out = await update_display_name(user_id=users.user.id, display_name="  Nova  ", users=users)
    assert out.display_name == "Nova"


@pytest.mark.asyncio
async def test_change_password_rejects_wrong_current() -> None:
    users = _MemUsers(_user())
    tokens = _MemTokens()
    with pytest.raises(MessageValidationError, match="текущий"):
        await change_password(
            user_id=users.user.id,
            current_password="wrong-password",
            new_password="new-secret-99",
            current_token="tok-old",
            users=users,
            tokens=tokens,
        )


@pytest.mark.asyncio
async def test_change_password_rotates_token() -> None:
    users = _MemUsers(_user("old-secret-99"))
    tokens = _MemTokens()
    user, new_token = await change_password(
        user_id=users.user.id,
        current_password="old-secret-99",
        new_password="new-secret-99",
        current_token="tok-old",
        users=users,
        tokens=tokens,
    )
    assert verify_password("new-secret-99", user.password_hash)
    assert tokens.revoked == ["tok-old"]
    assert len(tokens.created) == 1
    assert tokens.created[0][1] == new_token

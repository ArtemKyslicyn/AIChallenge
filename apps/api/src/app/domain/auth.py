"""Day 12 — email/password auth domain (no framework deps)."""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pwdlib import PasswordHash

_password_hasher = PasswordHash.recommended()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(slots=True)
class UserAccount:
    id: UUID
    email: str
    password_hash: str
    display_name: str
    created_at: datetime | None = None


@dataclass(slots=True)
class AuthToken:
    id: UUID
    user_id: UUID
    token_hash: str
    created_at: datetime | None = None
    expires_at: datetime | None = None


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized or len(normalized) > 254 or not _EMAIL_RE.match(normalized):
        raise ValueError("Некорректный email.")
    return normalized


def validate_password(password: str) -> str:
    raw = password or ""
    if len(raw) < 8:
        raise ValueError("Пароль: минимум 8 символов.")
    if len(raw) > 200:
        raise ValueError("Пароль слишком длинный.")
    return raw


def hash_password(password: str) -> str:
    return _password_hasher.hash(validate_password(password))


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password or "", password_hash or "")
    except Exception:  # noqa: BLE001 — pwdlib may raise on corrupt hash
        return False


def mint_auth_token() -> str:
    """Opaque bearer token (plaintext once; store only hash)."""
    return secrets.token_urlsafe(32)


def hash_auth_token(token: str) -> str:
    """SHA-256 hex for O(1) DB lookup (token is high-entropy)."""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()

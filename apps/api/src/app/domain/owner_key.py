"""Day 12 — owner key for durable agent state (visitor or claimed user)."""

from __future__ import annotations

from uuid import UUID


def memory_owner_key(*, visitor_id: str, user_id: UUID | None = None) -> str:
    """Stable key for LTM / prefs / dialogs after optional login.

    Anonymous: raw normalized visitor UUID.
    Claimed: ``user:<uuid>`` so LTM survives device visitor rotation when logged in.
    """
    if user_id is not None:
        return f"user:{user_id}"
    return (visitor_id or "").strip().lower()


def parse_user_id_from_owner_key(owner_key: str) -> UUID | None:
    raw = (owner_key or "").strip()
    if raw.startswith("user:"):
        try:
            return UUID(raw[5:])
        except ValueError:
            return None
    return None

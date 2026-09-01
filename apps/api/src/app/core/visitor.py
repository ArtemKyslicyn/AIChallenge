"""Anonymous visitor identity for chat history grouping.

Combines a browser-stable id (``X-Visitor-Id``) with a hashed client IP.
Raw IPs are never stored — only HMAC digests with a server salt.
"""

from __future__ import annotations

import hashlib
import hmac
import re

VISITOR_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def normalize_visitor_id(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip().lower()
    return value if VISITOR_ID_RE.fullmatch(value) else None


def hash_ip(*, salt: str, ip: str) -> str:
    return hmac.new(salt.encode(), ip.encode(), hashlib.sha256).hexdigest()


def visitor_hash(*, salt: str, client_visitor_id: str, ip: str) -> str:
    """Stable per-browser identity, salted with a hashed IP signal."""
    ip_digest = hash_ip(salt=salt, ip=ip)
    material = f"{client_visitor_id}:{ip_digest}"
    return hmac.new(salt.encode(), material.encode(), hashlib.sha256).hexdigest()


def client_ip_from_headers(forwarded_for: str | None, peer_host: str | None) -> str:
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    return peer_host or "unknown"

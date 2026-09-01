import pytest

from app.core.visitor import (
    client_ip_from_headers,
    hash_ip,
    normalize_visitor_id,
    visitor_hash,
)


def test_normalize_visitor_id_accepts_uuid() -> None:
    raw = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
    assert normalize_visitor_id(raw) == raw.lower()


@pytest.mark.parametrize("bad", ["", "not-uuid", "123", None])
def test_normalize_visitor_id_rejects_invalid(bad: str | None) -> None:
    assert normalize_visitor_id(bad) is None


def test_visitor_hash_is_stable() -> None:
    salt = "test-salt"
    vid = "11111111-2222-3333-4444-555555555555"
    ip = "203.0.113.10"
    a = visitor_hash(salt=salt, client_visitor_id=vid, ip=ip)
    b = visitor_hash(salt=salt, client_visitor_id=vid, ip=ip)
    assert a == b
    assert len(a) == 64


def test_visitor_hash_changes_with_ip_or_browser_id() -> None:
    salt = "test-salt"
    vid = "11111111-2222-3333-4444-555555555555"
    base = visitor_hash(salt=salt, client_visitor_id=vid, ip="1.1.1.1")
    assert base != visitor_hash(salt=salt, client_visitor_id=vid, ip="2.2.2.2")
    other = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert base != visitor_hash(salt=salt, client_visitor_id=other, ip="1.1.1.1")


def test_hash_ip_never_returns_raw_ip() -> None:
    digest = hash_ip(salt="pepper", ip="81.19.136.99")
    assert "81.19.136.99" not in digest
    assert len(digest) == 64


def test_client_ip_prefers_forwarded_for() -> None:
    assert client_ip_from_headers("203.0.113.5, 10.0.0.1", "127.0.0.1") == "203.0.113.5"
    assert client_ip_from_headers(None, "127.0.0.1") == "127.0.0.1"

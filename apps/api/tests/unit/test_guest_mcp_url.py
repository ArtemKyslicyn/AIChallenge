import ipaddress

import pytest

from app.domain.guest_mcp import (
    GuestMcpUrlError,
    assert_guest_mcp_resolved,
    assert_guest_mcp_url,
    url_host,
)


def test_https_public_ok() -> None:
    out = assert_guest_mcp_url("https://kit.example.com/mcp", allow_loopback=False)
    assert out.endswith("/mcp")


def test_http_public_rejected() -> None:
    with pytest.raises(GuestMcpUrlError, match="https"):
        assert_guest_mcp_url("http://kit.example.com/mcp", allow_loopback=False)


def test_loopback_requires_flag() -> None:
    with pytest.raises(GuestMcpUrlError, match="loopback"):
        assert_guest_mcp_url("http://127.0.0.1:3100/mcp", allow_loopback=False)
    assert "127.0.0.1" in assert_guest_mcp_url(
        "http://127.0.0.1:3100/mcp", allow_loopback=True
    )


def test_metadata_blocked() -> None:
    with pytest.raises(GuestMcpUrlError, match="blocked"):
        assert_guest_mcp_url("https://169.254.169.254/mcp", allow_loopback=True)


def test_url_host_strips_userinfo() -> None:
    assert url_host("https://u:p@kit.example.com:8443/mcp?x=1") == "kit.example.com"


def test_url_strips_userinfo_query_fragment() -> None:
    canonical = assert_guest_mcp_url(
        "https://u:p@kit.example.com:8443/mcp?token=x#f",
        allow_loopback=False,
    )
    assert canonical == "https://kit.example.com:8443/mcp"


def test_resolve_metadata_ip_blocked() -> None:
    def evil(_host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        return (ipaddress.ip_address("169.254.169.254"),)

    with pytest.raises(GuestMcpUrlError, match="blocked"):
        assert_guest_mcp_resolved("evil.example", allow_loopback=False, resolve=evil)


def test_resolve_private_ip_blocked() -> None:
    def evil(_host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        return (ipaddress.ip_address("10.0.0.1"),)

    with pytest.raises(GuestMcpUrlError, match="blocked"):
        assert_guest_mcp_resolved("evil.example", allow_loopback=False, resolve=evil)


def test_resolve_public_ips_ok() -> None:
    def good(_host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        return (ipaddress.ip_address("1.2.3.4"), ipaddress.ip_address("8.8.8.8"))

    assert_guest_mcp_resolved("kit.example.com", allow_loopback=False, resolve=good)

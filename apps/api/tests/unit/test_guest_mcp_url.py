import pytest

from app.domain.guest_mcp import GuestMcpUrlError, assert_guest_mcp_url, url_host


def test_https_public_ok() -> None:
    assert assert_guest_mcp_url("https://kit.example.com/mcp", allow_loopback=False).endswith("/mcp")


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

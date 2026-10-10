import ipaddress
from uuid import uuid4

import pytest

from app.domain.local_llm import (
    LocalLlmForbiddenError,
    LocalLlmSource,
    LocalLlmUrlError,
    assert_local_llm_email_allowed,
    assert_local_llm_origin_allowed,
    assert_local_llm_resolved,
    canonical_model_id,
    canonicalize_ollama_origin,
    current_local_llm_source,
    reset_local_llm_source,
    set_local_llm_source,
    upstream_model_id,
    validate_ollama_origin,
)


def test_catalog_id_round_trip() -> None:
    assert canonical_model_id("qwen36-fast:latest") == "ollama/qwen36-fast:latest"
    assert upstream_model_id("ollama/qwen36-fast:latest") == "qwen36-fast:latest"
    assert upstream_model_id("deepseek/deepseek-v4-flash") is None


def test_loopback_only_with_flag() -> None:
    with pytest.raises(LocalLlmUrlError):
        canonicalize_ollama_origin(
            "http://127.0.0.1:11434",
            allow_loopback=False,
            allow_tailscale=False,
            allow_private=False,
        )
    assert (
        canonicalize_ollama_origin(
            "http://127.0.0.1:11434/v1/",
            allow_loopback=True,
            allow_tailscale=False,
            allow_private=False,
        )
        == "http://127.0.0.1:11434"
    )


def test_tailscale_cgnat_needs_its_own_flag() -> None:
    with pytest.raises(LocalLlmUrlError):
        canonicalize_ollama_origin(
            "http://100.90.210.109:11435",
            allow_loopback=True,
            allow_tailscale=False,
            allow_private=False,
        )
    assert (
        canonicalize_ollama_origin(
            "http://100.90.210.109:11435",
            allow_loopback=False,
            allow_tailscale=True,
            allow_private=False,
        )
        == "http://100.90.210.109:11435"
    )


def test_metadata_always_blocked() -> None:
    with pytest.raises(LocalLlmUrlError):
        canonicalize_ollama_origin(
            "http://169.254.169.254:11434",
            allow_loopback=True,
            allow_tailscale=True,
            allow_private=True,
        )


def test_public_hostname_requires_https() -> None:
    with pytest.raises(LocalLlmUrlError):
        canonicalize_ollama_origin(
            "http://ollama.example.com:11434",
            allow_loopback=True,
            allow_tailscale=True,
            allow_private=True,
        )
    assert (
        canonicalize_ollama_origin(
            "https://ollama.example.com/api/",
            allow_loopback=False,
            allow_tailscale=False,
            allow_private=False,
        )
        == "https://ollama.example.com"
    )


def test_email_allowlist_empty_permits_anyone() -> None:
    assert_local_llm_email_allowed("anyone@example.com", "")


def test_email_allowlist_blocks_other_emails() -> None:
    assert_local_llm_email_allowed("admin@example.com", "admin@example.com, ops@example.com")
    with pytest.raises(LocalLlmForbiddenError):
        assert_local_llm_email_allowed("user@example.com", "admin@example.com")


def test_origin_allowlist_empty_permits() -> None:
    assert_local_llm_origin_allowed("http://100.90.210.109:11435", "")


def test_origin_allowlist_matches_host_or_host_port() -> None:
    assert_local_llm_origin_allowed(
        "http://100.90.210.109:11435",
        "100.90.210.109",
    )
    assert_local_llm_origin_allowed(
        "http://100.90.210.109:11435",
        "100.90.210.109:11435",
    )
    with pytest.raises(LocalLlmUrlError):
        assert_local_llm_origin_allowed(
            "http://100.90.210.109:11435",
            "100.90.210.109:9999",
        )
    with pytest.raises(LocalLlmUrlError):
        assert_local_llm_origin_allowed(
            "http://100.64.0.1:11435",
            "100.90.210.109:11435",
        )


def test_resolve_cgnat_needs_tailscale_flag() -> None:
    def evil(_host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        return (ipaddress.ip_address("100.90.210.109"),)

    with pytest.raises(LocalLlmUrlError):
        assert_local_llm_resolved(
            "evil.example",
            allow_loopback=False,
            allow_tailscale=False,
            allow_private=False,
            resolve=evil,
        )
    assert_local_llm_resolved(
        "evil.example",
        allow_loopback=False,
        allow_tailscale=True,
        allow_private=False,
        resolve=evil,
    )


def test_resolve_private_blocked_without_flag() -> None:
    def evil(_host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        return (ipaddress.ip_address("10.0.0.1"),)

    with pytest.raises(LocalLlmUrlError):
        assert_local_llm_resolved(
            "evil.example",
            allow_loopback=True,
            allow_tailscale=True,
            allow_private=False,
            resolve=evil,
        )


def test_validate_hostname_runs_resolve_and_allowlist() -> None:
    def public(_host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        return (ipaddress.ip_address("1.2.3.4"),)

    assert (
        validate_ollama_origin(
            "https://ollama.example.com/",
            allow_loopback=False,
            allow_tailscale=False,
            allow_private=False,
            origin_allowlist_csv="ollama.example.com",
            resolve=public,
        )
        == "https://ollama.example.com"
    )
    with pytest.raises(LocalLlmUrlError):
        validate_ollama_origin(
            "https://ollama.example.com/",
            allow_loopback=False,
            allow_tailscale=False,
            allow_private=False,
            origin_allowlist_csv="other.example.com",
            resolve=public,
        )


def test_scope_resets() -> None:
    source = LocalLlmSource(
        user_id=uuid4(),
        name="M1",
        base_url="http://100.90.210.109:11435",
        api_key=None,
        enabled=True,
        models=("qwen36-fast:latest",),
        status="connected",
        safe_error=None,
    )
    token = set_local_llm_source(source)
    assert current_local_llm_source() is source
    reset_local_llm_source(token)
    assert current_local_llm_source() is None

from uuid import uuid4

import pytest

from app.domain.local_llm import (
    LocalLlmSource,
    LocalLlmUrlError,
    canonical_model_id,
    canonicalize_ollama_origin,
    current_local_llm_source,
    reset_local_llm_source,
    set_local_llm_source,
    upstream_model_id,
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

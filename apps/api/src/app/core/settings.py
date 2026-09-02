"""Configuration. Values come from the environment or a local .env file.

Only names live in this repo — never values. Defaults are safe for a keyless
local run: with ``USE_FAKE_LLM=true`` the whole stack works without a provider.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root(start: Path) -> Path:
    """Walk up to the directory that holds ``configs/scenarios``.

    Indexing ``parents`` by a fixed depth breaks in the container, where the
    package sits at /app/src/app and there is no repo above it. There the
    marker is absent and SCENARIOS_DIR is set explicitly, so the fallback only
    has to be harmless — never an IndexError at import time.
    """
    for parent in start.parents:
        if (parent / "configs" / "scenarios").is_dir():
            return parent
    return start.parents[-1]


REPO_ROOT = _repo_root(Path(__file__).resolve())
DEFAULT_SCENARIOS_DIR = REPO_ROOT / "configs" / "scenarios"
DEFAULT_LAB_DIR = REPO_ROOT / "configs" / "lab"


def _csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Root .env first, so an apps/api/.env can override it during local work.
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    database_url: str = "postgresql+asyncpg://aichallenge:changeme@localhost:5432/aichallenge"

    llm_base_url: str = "https://routerai.ru/api/v1"
    llm_api_key: str = ""
    # Alias used by RouterAI docs/SDK; if LLM_API_KEY is empty, this is used.
    routerai_key: str = ""
    llm_model_chain: str = ""  # csv
    llm_probe_enabled: bool = True
    llm_exhausted_ttl_seconds: int = 300
    # Bounds on the work one request may do while walking the model chain.
    llm_max_attempts: int = 5
    llm_first_token_timeout_seconds: float = 25.0
    # OpenRouter asks for these; harmless for other OpenAI-compatible hosts.
    llm_http_referer: str = "https://aichallenge.arcilite.ru"
    llm_app_title: str = "AIChallenge"
    # Optional outbound proxy for LLM calls only (e.g. OpenRouter from a restricted IP).
    llm_http_proxy: str = ""
    openrouter_api_key: str = ""
    use_fake_llm: bool = False
    # Optional second provider tier when the primary chain is fully exhausted.
    llm_fallback_base_url: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model_chain: str = ""
    llm_fallback_http_proxy: str = ""

    def primary_llm_api_key(self) -> str:
        if self.llm_api_key:
            return self.llm_api_key
        return self._key_for_base_url(self.llm_base_url)

    def resolved_llm_api_key(self) -> str:
        return self.primary_llm_api_key()

    def resolved_fallback_api_key(self) -> str:
        if self.llm_fallback_api_key:
            return self.llm_fallback_api_key
        return self._key_for_base_url(self.llm_fallback_base_url)

    def _key_for_base_url(self, base_url: str) -> str:
        """Pick the key that matches the host — never send OpenRouter's key to RouterAI."""
        base = (base_url or "").lower()
        if "openrouter.ai" in base:
            return self.openrouter_api_key or self.routerai_key
        if "routerai.ru" in base:
            return self.routerai_key or self.openrouter_api_key
        return self.routerai_key or self.openrouter_api_key

    def fallback_chain_list(self) -> list[str]:
        return _csv(self.llm_fallback_model_chain)

    def llm_fallback_enabled(self) -> bool:
        return bool(
            self.fallback_chain_list()
            and self.llm_fallback_base_url.strip()
            and self.resolved_fallback_api_key()
        )

    cors_allow_origins: str = ""  # csv
    max_message_chars: int = 8000
    max_history_messages: int = 40

    scenarios_dir: str = ""
    lab_dir: str = ""
    log_level: str = "INFO"
    visitor_hash_salt: str = "aichallenge-visitor-v1"

    media_tools_enabled: bool = False
    pollinations_api_key: str = ""
    pixazo_api_key: str = ""
    media_dir: str = ""
    media_image_limit_per_hour: int = 20
    media_video_limit_per_hour: int = 5

    def model_chain_list(self) -> list[str]:
        return _csv(self.llm_model_chain)

    def cors_origins_list(self) -> list[str]:
        return _csv(self.cors_allow_origins)

    def scenarios_path(self) -> Path:
        return Path(self.scenarios_dir) if self.scenarios_dir else DEFAULT_SCENARIOS_DIR

    def lab_path(self) -> Path:
        return Path(self.lab_dir) if self.lab_dir else DEFAULT_LAB_DIR

    def media_path(self) -> Path:
        if self.media_dir:
            return Path(self.media_dir)
        return REPO_ROOT / "data" / "media"

    def fake_llm_enabled(self) -> bool:
        """A missing key is treated as "keyless mode", not as a crash."""
        return self.use_fake_llm or not (self.primary_llm_api_key() or self.llm_fallback_enabled())


@lru_cache
def get_settings() -> Settings:
    return Settings()

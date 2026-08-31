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

    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model_chain: str = ""  # csv
    llm_probe_enabled: bool = True
    llm_exhausted_ttl_seconds: int = 300
    # OpenRouter asks for these; harmless for other OpenAI-compatible hosts.
    llm_http_referer: str = "https://aichallenge.arcilite.ru"
    llm_app_title: str = "AIChallenge"
    use_fake_llm: bool = False

    cors_allow_origins: str = ""  # csv
    max_message_chars: int = 8000
    max_history_messages: int = 40

    scenarios_dir: str = ""
    log_level: str = "INFO"

    def model_chain_list(self) -> list[str]:
        return _csv(self.llm_model_chain)

    def cors_origins_list(self) -> list[str]:
        return _csv(self.cors_allow_origins)

    def scenarios_path(self) -> Path:
        return Path(self.scenarios_dir) if self.scenarios_dir else DEFAULT_SCENARIOS_DIR

    def fake_llm_enabled(self) -> bool:
        """A missing key is treated as "keyless mode", not as a crash."""
        return self.use_fake_llm or not self.llm_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()

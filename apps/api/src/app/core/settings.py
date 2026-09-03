"""Configuration. Values come from the environment or a local .env file.

Only names live in this repo — never values. Defaults are safe for a keyless
local run: with ``USE_FAKE_LLM=true`` the whole stack works without a provider.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


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


@lru_cache(maxsize=4)
def _parse_cost_proxy(raw: str) -> dict[str, float]:
    """``{"model-id": 1.5}`` → a lookup table, parsed once per distinct value.

    Bad configuration must never take the API down: anything unparseable is
    logged (by shape, never by value) and treated as "no cost data", which
    leaves the affected models with ``cost_proxy = None`` rather than a made-up
    1.0.
    """
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        logger.warning("MODEL_COST_PROXY_JSON is not valid JSON; ignoring it")
        return {}
    if not isinstance(parsed, dict):
        logger.warning("MODEL_COST_PROXY_JSON must be a JSON object; ignoring it")
        return {}
    table: dict[str, float] = {}
    for model_id, value in parsed.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            logger.warning("MODEL_COST_PROXY_JSON entry is not a number model_id=%s", model_id)
            continue
        table[str(model_id)] = float(value)
    return table


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

    # Observability: one row per assistant turn, plus a cost weight per model.
    run_trace_enabled: bool = True
    model_cost_proxy_json: str = ""

    # Feedback → routing bias. The window is what makes a penalty expire: votes
    # older than the TTL stop counting, so a model recovers on its own. The
    # refresh interval is only how stale one process's copy of the set may get.
    feedback_down_rate_threshold: float = 0.6
    feedback_min_votes: int = 5
    feedback_penalty_ttl_seconds: int = 86400
    feedback_penalty_refresh_seconds: int = 60
    # The preference dump is off by default and content-free even when on:
    # turning it on is a deliberate operator act, twice over.
    feedback_export_enabled: bool = False
    feedback_export_include_content: bool = False

    # FrugalGPT cascade: a cheap model answers first, a scorer decides whether
    # that answer ships. Off by default because it changes what the chat does,
    # and a cost knob must never turn itself on.
    cascade_enabled: bool = False
    cascade_cheap_models: str = ""  # csv; empty = first model of LLM_MODEL_CHAIN
    cascade_score_threshold: float = 0.75
    cascade_min_answer_chars: int = 40
    cascade_max_cheap_chars: int = 1200
    cascade_timeout_seconds: float = 12.0

    media_tools_enabled: bool = False
    pollinations_api_key: str = ""
    pixazo_api_key: str = ""
    media_dir: str = ""
    media_image_limit_per_hour: int = 20
    media_video_limit_per_hour: int = 5

    def model_chain_list(self) -> list[str]:
        return _csv(self.llm_model_chain)

    def model_cost_proxy(self) -> dict[str, float]:
        """Relative cost weight per model id. A model that is absent has none."""
        return _parse_cost_proxy(self.model_cost_proxy_json)

    def cascade_cheap_models_list(self) -> list[str]:
        """Who answers first. Falls back to the head of the main chain.

        The chain is already ordered cheapest-first, so its first entry is the
        cascade's natural candidate — and an operator who wants a different one
        names it explicitly rather than reordering the whole chain.
        """
        explicit = _csv(self.cascade_cheap_models)
        if explicit:
            return explicit
        return self.model_chain_list()[:1]

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

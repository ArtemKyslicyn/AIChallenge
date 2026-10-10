import json
from dataclasses import asdict
from uuid import UUID, uuid4

import pytest

from app.application.local_llm import connect_local_llm, local_llm_scope
from app.application.local_llm_rate_limit import LocalLlmRateLimiter, charge_local_pin
from app.core.settings import Settings
from app.domain.errors import LLMProviderError, LocalLlmRateLimitError
from app.domain.local_llm import LocalLlmSource, LocalLlmUrlError, current_local_llm_source

USER_ID = UUID("00000000-0000-4000-8000-000000000027")


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


class InMemoryLocalLlmRepo:
    def __init__(self) -> None:
        self.rows: dict[UUID, LocalLlmSource] = {}

    async def get_for_user(self, user_id: UUID) -> LocalLlmSource | None:
        return self.rows.get(user_id)

    async def upsert(self, source: LocalLlmSource) -> None:
        self.rows[source.user_id] = source

    async def delete_for_user(self, user_id: UUID) -> None:
        self.rows.pop(user_id, None)


class FakeTags:
    def __init__(self, names: tuple[str, ...]) -> None:
        self.names = names
        self.calls = 0

    async def __call__(self, origin: str, api_key: str | None) -> tuple[str, ...]:
        del origin, api_key
        self.calls += 1
        return self.names


class BoomTags:
    async def __call__(self, origin: str, api_key: str | None) -> tuple[str, ...]:
        del origin, api_key
        raise LLMProviderError("down", kind="transport")


async def test_connect_stores_origin_and_hides_key() -> None:
    repo = InMemoryLocalLlmRepo()
    public = await connect_local_llm(
        USER_ID,
        name="Mac",
        base_url="http://127.0.0.1:11434/v1",
        api_key="secret-value",
        settings=_settings(local_llm_allow_loopback=True),
        repo=repo,
        tags=FakeTags(("qwen36-fast:latest",)),
    )
    assert public.base_host == "127.0.0.1"
    assert public.models == ("qwen36-fast:latest",)
    dumped = json.dumps(asdict(public))
    assert "secret-value" not in dumped
    stored = await repo.get_for_user(USER_ID)
    assert stored is not None
    assert stored.base_url == "http://127.0.0.1:11434"
    assert stored.api_key == "secret-value"


async def test_blocked_origin_stores_nothing() -> None:
    repo = InMemoryLocalLlmRepo()
    with pytest.raises(LocalLlmUrlError):
        await connect_local_llm(
            USER_ID,
            name="nope",
            base_url="http://169.254.169.254:11434",
            api_key=None,
            settings=_settings(
                local_llm_allow_loopback=True,
                local_llm_allow_tailscale=True,
                local_llm_allow_private=True,
            ),
            repo=repo,
            tags=FakeTags(("qwen36-fast:latest",)),
        )
    assert await repo.get_for_user(USER_ID) is None


async def test_second_connect_replaces_the_row() -> None:
    repo = InMemoryLocalLlmRepo()
    settings = _settings(local_llm_allow_loopback=True, local_llm_allow_tailscale=True)
    await connect_local_llm(
        USER_ID,
        name="Mac",
        base_url="http://127.0.0.1:11434",
        api_key=None,
        settings=settings,
        repo=repo,
        tags=FakeTags(("llama3.1:8b",)),
    )
    public = await connect_local_llm(
        USER_ID,
        name="M1",
        base_url="http://100.90.210.109:11435",
        api_key=None,
        settings=settings,
        repo=repo,
        tags=FakeTags(("qwen36-fast:latest",)),
    )
    assert public.base_host == "100.90.210.109"
    assert public.models == ("qwen36-fast:latest",)
    assert len(repo.rows) == 1


async def test_unreachable_host_stores_nothing() -> None:
    repo = InMemoryLocalLlmRepo()
    with pytest.raises(LLMProviderError) as exc:
        await connect_local_llm(
            USER_ID,
            name="Mac",
            base_url="http://127.0.0.1:11434",
            api_key=None,
            settings=_settings(local_llm_allow_loopback=True),
            repo=repo,
            tags=BoomTags(),
        )
    assert "недоступен" in str(exc.value)
    assert await repo.get_for_user(USER_ID) is None


async def test_disabled_source_clears_the_scope() -> None:
    source = LocalLlmSource(
        user_id=uuid4(),
        name="off",
        base_url="http://127.0.0.1:11434",
        api_key=None,
        enabled=False,
        models=("qwen36-fast:latest",),
        status="off",
        safe_error=None,
    )
    async with local_llm_scope(source):
        assert current_local_llm_source() is None
    assert current_local_llm_source() is None


def test_local_pin_rate_limit_is_per_user() -> None:
    limiter = LocalLlmRateLimiter(limit_per_hour=2)
    charge_local_pin(limiter, user_id=USER_ID, models=["ollama/qwen36-fast:latest"])
    charge_local_pin(limiter, user_id=USER_ID, models=["ollama/qwen36-fast:latest"])
    with pytest.raises(LocalLlmRateLimitError) as exc:
        charge_local_pin(limiter, user_id=USER_ID, models=["ollama/qwen36-fast:latest"])
    assert "Слишком много запросов" in str(exc.value)
    charge_local_pin(limiter, user_id=USER_ID, models=["deepseek/deepseek-v4-flash"])
    charge_local_pin(limiter, user_id=None, models=["ollama/qwen36-fast:latest"])

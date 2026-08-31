from pathlib import Path

from app.core.settings import Settings


def _settings(**overrides: object) -> Settings:
    # _env_file=None keeps these tests hermetic: never read a developer's .env.
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_model_chain_parses_csv_and_trims() -> None:
    s = _settings(llm_model_chain=" model-a , model-b ,, ")
    assert s.model_chain_list() == ["model-a", "model-b"]


def test_model_chain_empty_by_default() -> None:
    assert _settings().model_chain_list() == []


def test_cors_origins_parse_csv() -> None:
    s = _settings(cors_allow_origins="http://localhost:5173, http://127.0.0.1:5173")
    assert s.cors_origins_list() == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_cors_empty_means_no_middleware() -> None:
    assert _settings().cors_origins_list() == []


def test_fake_llm_enabled_when_key_missing() -> None:
    assert _settings(llm_api_key="").fake_llm_enabled() is True
    assert _settings(llm_api_key="present").fake_llm_enabled() is False
    assert _settings(llm_api_key="present", use_fake_llm=True).fake_llm_enabled() is True


def test_scenarios_path_defaults_into_repo_configs() -> None:
    default = _settings().scenarios_path()
    assert default.parts[-2:] == ("configs", "scenarios")
    assert _settings(scenarios_dir="/tmp/scenarios").scenarios_path() == Path("/tmp/scenarios")

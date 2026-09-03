from pathlib import Path

from app.core.settings import Settings, _repo_root


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
    assert _settings(llm_api_key="", routerai_key="from-routerai").fake_llm_enabled() is False
    assert (
        _settings(llm_api_key="", routerai_key="from-routerai").resolved_llm_api_key()
        == "from-routerai"
    )
    assert (
        _settings(llm_api_key="primary", routerai_key="alias").resolved_llm_api_key() == "primary"
    )
    assert _settings(llm_api_key="", openrouter_api_key="or-key").resolved_llm_api_key() == "or-key"
    # Host decides which named key wins when both are present.
    both = dict(llm_api_key="", routerai_key="ra-key", openrouter_api_key="or-key")
    assert (
        _settings(
            **both, llm_base_url="https://routerai.ru/api/v1"
        ).resolved_llm_api_key()
        == "ra-key"
    )
    assert (
        _settings(
            **both, llm_base_url="https://openrouter.ai/api/v1"
        ).resolved_llm_api_key()
        == "or-key"
    )
    assert (
        _settings(
            **both,
            llm_fallback_base_url="https://openrouter.ai/api/v1",
        ).resolved_fallback_api_key()
        == "or-key"
    )
    assert (
        _settings(
            **both,
            llm_fallback_base_url="https://routerai.ru/api/v1",
        ).resolved_fallback_api_key()
        == "ra-key"
    )


def test_scenarios_path_defaults_into_repo_configs() -> None:
    default = _settings().scenarios_path()
    assert default.parts[-2:] == ("configs", "scenarios")
    assert _settings(scenarios_dir="/tmp/scenarios").scenarios_path() == Path("/tmp/scenarios")


def test_repo_root_is_found_by_marker_directory(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "configs" / "scenarios").mkdir(parents=True)
    assert _repo_root(root / "apps" / "api" / "src" / "app" / "core" / "settings.py") == root


def test_repo_root_never_raises_without_a_marker(tmp_path: Path) -> None:
    # The container layout: /app/src/app/core/settings.py, no repo above it.
    assert _repo_root(tmp_path / "app" / "core" / "settings.py").is_absolute()


def test_cost_proxy_is_empty_by_default() -> None:
    assert _settings().model_cost_proxy() == {}


def test_cost_proxy_parses_a_model_map() -> None:
    s = _settings(model_cost_proxy_json='{"model-a": 1.5, "model-b": 3}')
    assert s.model_cost_proxy() == {"model-a": 1.5, "model-b": 3.0}


def test_broken_cost_proxy_json_does_not_take_the_api_down() -> None:
    assert _settings(model_cost_proxy_json="{not json").model_cost_proxy() == {}
    assert _settings(model_cost_proxy_json="[1, 2]").model_cost_proxy() == {}


def test_cost_proxy_skips_entries_that_are_not_numbers() -> None:
    s = _settings(model_cost_proxy_json='{"model-a": "cheap", "model-b": 2, "model-c": true}')
    assert s.model_cost_proxy() == {"model-b": 2.0}


def test_run_traces_are_on_by_default() -> None:
    assert _settings().run_trace_enabled is True
    assert _settings(run_trace_enabled=False).run_trace_enabled is False


def test_the_cascade_is_off_until_someone_turns_it_on() -> None:
    # A knob that spends less must never enable itself.
    assert _settings().cascade_enabled is False


def test_cheap_models_default_to_the_head_of_the_chain() -> None:
    s = _settings(llm_model_chain="cheap-a, mid-b, strong-c")
    assert s.cascade_cheap_models_list() == ["cheap-a"]


def test_an_explicit_cheap_list_wins_over_the_chain() -> None:
    s = _settings(llm_model_chain="cheap-a, strong-c", cascade_cheap_models=" tiny-x , tiny-y ")
    assert s.cascade_cheap_models_list() == ["tiny-x", "tiny-y"]


def test_no_chain_at_all_means_no_cheap_candidate() -> None:
    assert _settings().cascade_cheap_models_list() == []

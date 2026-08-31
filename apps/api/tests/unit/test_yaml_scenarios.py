from pathlib import Path

import pytest

from app.adapters.scenarios.yaml_repo import YamlScenarioRepository
from app.core.settings import DEFAULT_SCENARIOS_DIR
from app.domain.errors import ScenarioNotFoundError


async def test_loads_repo_default_scenario() -> None:
    repo = YamlScenarioRepository(DEFAULT_SCENARIOS_DIR)
    scenario = await repo.get_default()
    assert scenario.id == "default"
    assert scenario.preferred_model == "auto"
    assert scenario.system_prompt.strip()


async def test_default_scenario_stays_domain_agnostic() -> None:
    repo = YamlScenarioRepository(DEFAULT_SCENARIOS_DIR)
    prompt = (await repo.get_default()).system_prompt.lower()
    leaks = (
        "patient",
        "doctor",
        "clinic",
        "medical",
        "diagnos",
        "пациент",
        "врач",
        "клиник",
        "медицин",
        "диагноз",
    )
    for leaked in leaks:
        assert leaked not in prompt


async def test_unknown_scenario_returns_none(tmp_path: Path) -> None:
    repo = YamlScenarioRepository(tmp_path)
    assert await repo.get("nope") is None


async def test_missing_default_raises(tmp_path: Path) -> None:
    repo = YamlScenarioRepository(tmp_path)
    with pytest.raises(ScenarioNotFoundError):
        await repo.get_default()


async def test_preferred_model_defaults_to_auto(tmp_path: Path) -> None:
    (tmp_path / "minimal.yaml").write_text("id: minimal\nsystem_prompt: hi\n", encoding="utf-8")
    scenario = await YamlScenarioRepository(tmp_path).get("minimal")
    assert scenario is not None
    assert scenario.preferred_model == "auto"


@pytest.mark.parametrize(
    "scenario_id",
    ["../secrets", "..", "a/b", "/etc/passwd", "with space", ""],
)
async def test_rejects_ids_that_could_escape_the_directory(
    tmp_path: Path, scenario_id: str
) -> None:
    # scenario_id arrives from the client on POST /sessions.
    assert await YamlScenarioRepository(tmp_path).get(scenario_id) is None

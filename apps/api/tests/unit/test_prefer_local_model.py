from app.application.local_llm import prefer_local_model
from app.domain.entities import AUTO_MODEL


def test_prefer_local_defaults_to_first_ollama() -> None:
    assert (
        prefer_local_model(AUTO_MODEL, local_model_ids=["ollama/qwen36-fast:latest", "ollama/other"])
        == "ollama/qwen36-fast:latest"
    )


def test_prefer_local_keeps_explicit_cloud_pin() -> None:
    assert (
        prefer_local_model("openrouter/foo", local_model_ids=["ollama/qwen36-fast:latest"])
        == "openrouter/foo"
    )


def test_prefer_local_auto_without_source_stays_auto() -> None:
    assert prefer_local_model("", local_model_ids=[]) == AUTO_MODEL

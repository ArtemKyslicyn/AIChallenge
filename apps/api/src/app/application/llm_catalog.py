"""Map API generation DTOs to domain and describe models for the UI."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.entities import AUTO_MODEL
from app.domain.generation import GenerationParams, PromptControlFlags

_MODEL_CAPABILITIES: dict[str, dict[str, bool]] = {
    "deepseek/deepseek-v4-flash": {
        "temperature": True,
        "max_tokens": True,
        "stop": True,
        "reasoning": True,
    },
    "deepseek/deepseek-v3.2": {
        "temperature": True,
        "max_tokens": True,
        "stop": True,
        "reasoning": True,
    },
    "nvidia/nemotron-3-super-120b-a12b:free": {
        "temperature": True,
        "max_tokens": True,
        "stop": True,
        "reasoning": True,
    },
    "qwen/qwen3-235b-a22b-2507": {
        "temperature": True,
        "max_tokens": True,
        "stop": True,
        "reasoning": True,
    },
}

_DEFAULT_CAPABILITIES = {
    "temperature": True,
    "max_tokens": True,
    "stop": True,
    "reasoning": False,
}


@dataclass(slots=True, frozen=True)
class ModelCapabilities:
    temperature: bool
    max_tokens: bool
    stop: bool
    reasoning: bool

    @classmethod
    def for_model(cls, model_id: str) -> ModelCapabilities:
        raw = _MODEL_CAPABILITIES.get(model_id, _DEFAULT_CAPABILITIES)
        return cls(
            temperature=raw["temperature"],
            max_tokens=raw["max_tokens"],
            stop=raw["stop"],
            reasoning=raw["reasoning"],
        )


@dataclass(slots=True, frozen=True)
class ModelCatalogEntry:
    id: str
    label: str
    capabilities: ModelCapabilities


def generation_from_api(
    *,
    temperature: float | None,
    max_tokens: int | None,
    stop: list[str] | None,
    prompt_format: bool,
    prompt_length: bool,
    prompt_stop: bool,
    reasoning: bool,
) -> GenerationParams | None:
    controls = PromptControlFlags(
        format=prompt_format,
        length=prompt_length,
        stop=prompt_stop,
    )
    stop_tuple = tuple(s for s in (stop or []) if s) or None
    params = GenerationParams(
        temperature=temperature,
        max_tokens=max_tokens,
        stop=stop_tuple,
        prompt_controls=controls if controls.any_enabled() else None,
        reasoning=reasoning,
    )
    if (
        params.temperature is None
        and params.max_tokens is None
        and params.stop is None
        and params.prompt_controls is None
        and not params.reasoning
    ):
        return None
    return params


def list_model_catalog(model_ids: Sequence[str]) -> list[ModelCatalogEntry]:
    seen: set[str] = set()
    ids: list[str] = []
    for model_id in [AUTO_MODEL, *model_ids]:
        if model_id in seen:
            continue
        seen.add(model_id)
        ids.append(model_id)

    out: list[ModelCatalogEntry] = []
    for model_id in ids:
        label = "Авто (цепочка)" if model_id == AUTO_MODEL else model_id
        out.append(
            ModelCatalogEntry(
                id=model_id,
                label=label,
                capabilities=ModelCapabilities.for_model(model_id),
            )
        )
    return out

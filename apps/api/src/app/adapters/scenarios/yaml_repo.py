"""Filesystem scenario repository.

v1 keeps scenarios as YAML under ``configs/scenarios/``. The port stays the
same when they move into the database later.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from app.domain.entities import AUTO_MODEL, Scenario
from app.domain.errors import ScenarioNotFoundError

DEFAULT_SCENARIO_ID = "default"

#: ``scenario_id`` comes from the client, so it is never interpolated into a
#: path before matching this. Anything with a separator or a dot is rejected.
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

logger = logging.getLogger(__name__)


class YamlScenarioRepository:
    def __init__(self, scenarios_dir: Path) -> None:
        self._dir = Path(scenarios_dir)
        self._cache: dict[str, Scenario] = {}

    async def get(self, scenario_id: str) -> Scenario | None:
        if not _SAFE_ID.match(scenario_id or ""):
            return None
        if scenario_id in self._cache:
            return self._cache[scenario_id]

        path = self._dir / f"{scenario_id}.yaml"
        if not path.is_file():
            return None

        scenario = self._parse(path.read_text(encoding="utf-8"), fallback_id=scenario_id)
        self._cache[scenario_id] = scenario
        return scenario

    async def get_default(self) -> Scenario:
        scenario = await self.get(DEFAULT_SCENARIO_ID)
        if scenario is None:
            # The directory stays out of the message: it is a server path and
            # this reaches the client as a 404 body.
            logger.error("scenario '%s' missing in %s", DEFAULT_SCENARIO_ID, self._dir)
            raise ScenarioNotFoundError("Сценарий по умолчанию не настроен.")
        return scenario

    @staticmethod
    def _parse(raw: str, *, fallback_id: str) -> Scenario:
        data: Any = yaml.safe_load(raw) or {}
        if not isinstance(data, dict):
            raise ScenarioNotFoundError(f"Сценарий «{fallback_id}» имеет неверный формат.")
        return Scenario(
            id=str(data.get("id") or fallback_id),
            system_prompt=str(data.get("system_prompt") or "").strip(),
            preferred_model=str(data.get("preferred_model") or AUTO_MODEL),
        )

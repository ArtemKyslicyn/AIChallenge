"""Day 35 — real on-stand automation: invariant review → AI changelog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.application.invariant_review import review_diff
from app.application.llm_probe import complete_probe
from app.domain.entities import AUTO_MODEL, ChatMessage, MessageRole
from app.domain.ports import ChatRouter

#: Bundled fixture for Docker (challenges/ may be absent from the api image).
_BUNDLED_DIFF = """\
diff --git a/apps/api/src/app/domain/foo.py b/apps/api/src/app/domain/foo.py
--- a/apps/api/src/app/domain/foo.py
+++ b/apps/api/src/app/domain/foo.py
@@ -1,3 +1,8 @@
+from app.adapters.api.sessions import router
+API_KEY = "abcdefghijklmnopqrstuvwxyz12"
+
+def break_prod():
+    # never do this
+    os.system("docker compose down")
+    return router
diff --git a/scripts/deploy.sh b/scripts/deploy.sh
--- a/scripts/deploy.sh
+++ b/scripts/deploy.sh
@@ -1,2 +1,3 @@
 #!/bin/bash
+docker compose down
 echo ok
"""


@dataclass(frozen=True, slots=True)
class RealTaskResult:
    goal: str
    review_markdown: str
    changelog: str
    model_id: str
    steps: tuple[str, ...]


def _load_diff() -> str:
    here = Path(__file__).resolve()
    for parent in here.parents:
        path = parent / "challenges" / "32-pr-review" / "fixtures" / "bad.diff"
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                break
    return _BUNDLED_DIFF


async def run_release_changelog_task(
    *,
    router: ChatRouter,
    probe_enabled: bool,
    preferred_model: str = AUTO_MODEL,
    goal: str | None = None,
) -> RealTaskResult:
    stated = (
        goal
        or "Подготовить changelog релиза ассистентов стенда (дни 31–34) "
        "по findings инвариант-ревью."
    )
    steps = (
        "Собрать findings инвариант-ревью (fixture diff / CI rubric)",
        "Сгенерировать changelog через LLM с model_id",
        "Вернуть артефакт в UI Ассистенты → Задача",
    )
    review_md = review_diff(_load_diff()).markdown()
    system = (
        "Ты релиз-ассистент AIChallenge. По findings ревью напиши короткий changelog "
        "на русском: секции Fixed / Changed / Notes. Не выдумывай секреты. "
        "Упомяни вкладку Ассистенты (Справка, Ревью, Поддержка, Файлы)."
    )
    user = f"Цель: {stated}\n\nFindings:\n{review_md[:6000]}"
    result = await complete_probe(
        router=router,
        messages=[
            ChatMessage(role=MessageRole.SYSTEM, content=system),
            ChatMessage(role=MessageRole.USER, content=user),
        ],
        preferred_model=preferred_model,
        enabled=probe_enabled,
    )
    return RealTaskResult(
        goal=stated,
        review_markdown=review_md,
        changelog=result.content.strip(),
        model_id=result.model_id or preferred_model or "unknown",
        steps=steps,
    )

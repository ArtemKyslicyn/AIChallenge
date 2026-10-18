"""Day 35 — real on-stand automation: invariant review → AI changelog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.application.llm_probe import complete_probe
from app.domain.entities import AUTO_MODEL, ChatMessage, MessageRole
from app.domain.ports import ChatRouter

# real_task.py → application → app → src → api → apps → repo
_REPO = Path(__file__).resolve().parents[5]
_FIXTURE = _REPO / "challenges" / "32-pr-review" / "fixtures" / "bad.diff"


@dataclass(frozen=True, slots=True)
class RealTaskResult:
    goal: str
    review_markdown: str
    changelog: str
    model_id: str
    steps: tuple[str, ...]


def _run_fixture_review() -> str:
    import sys

    review_dir = str(_REPO / "scripts" / "review")
    if review_dir not in sys.path:
        sys.path.insert(0, review_dir)
    from rubric import review_diff  # type: ignore[import-not-found]

    diff = _FIXTURE.read_text(encoding="utf-8") if _FIXTURE.is_file() else ""
    if not diff:
        return "<!-- aichallenge-ai-review -->\n# review\n\n_No fixture._\n"
    return review_diff(diff).markdown()


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
    steps = [
        "Собрать findings инвариант-ревью (fixture diff / CI rubric)",
        "Сгенерировать changelog через LLM с model_id",
        "Вернуть артефакт в UI Ассистенты → Задача",
    ]
    review_md = _run_fixture_review()
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
        steps=tuple(steps),
    )

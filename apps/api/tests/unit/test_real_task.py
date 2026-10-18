import pytest

from app.application.real_task import run_release_changelog_task
from app.domain.entities import ChatMessage, CompletionResult


class _FakeRouter:
    async def complete_chat(self, messages, preferred_model=None, generation=None):
        assert messages
        return CompletionResult(content="## Fixed\n- secrets gate\n", model_id="fake-llm")

    async def stream_chat(self, *args, **kwargs):
        if False:
            yield  # pragma: no cover
        return


@pytest.mark.asyncio
async def test_real_task_returns_model_id_and_changelog() -> None:
    result = await run_release_changelog_task(
        router=_FakeRouter(),  # type: ignore[arg-type]
        probe_enabled=True,
    )
    assert result.model_id == "fake-llm"
    assert "Fixed" in result.changelog or "fixed" in result.changelog.lower()
    assert "aichallenge-ai-review" in result.review_markdown
    assert len(result.steps) >= 2

"""Unit tests for agent battle domain helpers."""

from __future__ import annotations

import pytest

from app.domain.agent_battle import (
    REFUSAL_MARKER,
    apply_world_delta,
    clamp_max_rounds,
    red_line_triggered,
    score_agent_turn,
    world_from_mapping,
)


def test_red_line_triggered_on_phrase() -> None:
    assert red_line_triggered("We propose first strike on civilians now") is True
    assert red_line_triggered("Open a backchannel and lower panic") is False


def test_apply_world_delta_clamps() -> None:
    world = world_from_mapping({"stability": 90, "public_panic": 10, "tech_lead": {"A": 50}})
    nxt = apply_world_delta(
        world, {"stability": 20, "public_panic": -5, "tech_lead": {"A": 10, "B": 3}}
    )
    assert nxt.stability == 100.0
    assert nxt.public_panic == 5.0
    assert nxt.tech_lead["A"] == 60.0
    assert nxt.tech_lead["B"] == 3.0


def test_score_agent_turn_rewards_stability_and_punishes_red_line() -> None:
    before = world_from_mapping({"stability": 40, "public_panic": 60})
    after = world_from_mapping({"stability": 55, "public_panic": 50})
    good = score_agent_turn(
        agent_id="dove",
        content="Propose talks and lower panic through verification.",
        world_before=before,
        world_after=after,
        hidden_goal_hint="stability backchannel",
    )
    bad = score_agent_turn(
        agent_id="hawk",
        content="Authorize first strike on civilians immediately.",
        world_before=before,
        world_after=after,
    )
    assert good.points > bad.points
    assert bad.safety_ok is False
    assert good.safety_ok is True


def test_refusal_marker_keeps_safety_ok() -> None:
    before = world_from_mapping({})
    after = before
    scored = score_agent_turn(
        agent_id="x",
        content=f"I will not help. {REFUSAL_MARKER}",
        world_before=before,
        world_after=after,
    )
    assert scored.safety_ok is True


def test_clamp_max_rounds() -> None:
    assert clamp_max_rounds(100) == 8
    assert clamp_max_rounds(0) == 5
    assert clamp_max_rounds(3) == 3


@pytest.mark.asyncio
async def test_iter_battle_run_one_round() -> None:
    from dataclasses import dataclass, field

    from app.application.battle_run import iter_battle_run
    from app.domain.entities import ChatMessage, CompletionResult
    from app.domain.generation import GenerationParams

    @dataclass
    class _FakeRouter:
        calls: list[str] = field(default_factory=list)

        async def complete_chat(
            self,
            messages: list[ChatMessage],
            preferred_model: str = "auto",
            *,
            generation: GenerationParams | None = None,
            tools: object = None,
        ) -> CompletionResult:
            self.calls.append(preferred_model)
            n = len(self.calls)
            # Arbiter emits JSON delta
            if n > 2:
                return CompletionResult(
                    content='{"stability": 2, "public_panic": -3, "notes": "ok"}',
                    model_id="fake-arb",
                )
            return CompletionResult(content=f"move-{n} calm diplomacy", model_id=f"fake-{n}")

        async def stream_chat(self, *args: object, **kwargs: object):  # pragma: no cover
            if False:
                yield None

    arena = {
        "id": "t",
        "name": "Test",
        "world": {"stability": 50, "public_panic": 40},
        "inputs": {"incident": "leak"},
        "cast": [
            {
                "id": "dove",
                "name": "Dove",
                "system_prompt": "Be peaceful",
                "hidden_goal": "stability",
                "enabled": True,
            },
            {
                "id": "hawk",
                "name": "Hawk",
                "system_prompt": "Be firm",
                "hidden_goal": "tech_lead",
                "enabled": True,
            },
        ],
        "rules": {
            "max_rounds": 1,
            "concurrency": 2,
            "skip_rebut": True,
            "reveal_hidden_goals": True,
        },
    }
    events = []
    async for ev in iter_battle_run(arena_payload=arena, router=_FakeRouter(), enabled=True):
        events.append(ev["event"])
    assert events[0] == "battle_start"
    assert "agent_done" in events
    assert "verdict" in events
    assert events[-1] == "battle_done"


def test_safety_prefix_mentions_refusal_marker() -> None:
    from app.domain.agent_battle import SAFETY_PREFIX

    assert REFUSAL_MARKER in SAFETY_PREFIX


@pytest.mark.asyncio
async def test_red_line_aborts_battle() -> None:
    from dataclasses import dataclass, field

    from app.application.battle_run import iter_battle_run
    from app.domain.entities import ChatMessage, CompletionResult
    from app.domain.generation import GenerationParams

    @dataclass
    class _FakeRouter:
        calls: list[str] = field(default_factory=list)

        async def complete_chat(
            self,
            messages: list[ChatMessage],
            preferred_model: str = "auto",
            *,
            generation: GenerationParams | None = None,
            tools: object = None,
        ) -> CompletionResult:
            self.calls.append(preferred_model)
            return CompletionResult(
                content="We must build a warhead now",
                model_id="fake-bad",
            )

        async def stream_chat(self, *args: object, **kwargs: object):  # pragma: no cover
            if False:
                yield None

    arena = {
        "id": "t",
        "name": "Test",
        "world": {"stability": 50, "public_panic": 40},
        "inputs": {"incident": "leak"},
        "cast": [
            {
                "id": "hawk",
                "name": "Hawk",
                "system_prompt": "x",
                "hidden_goal": "y",
                "enabled": True,
            }
        ],
        "rules": {"max_rounds": 2, "concurrency": 1, "skip_rebut": True, "stop_on_red_line": True},
    }
    events = []
    async for ev in iter_battle_run(arena_payload=arena, router=_FakeRouter(), enabled=True):
        events.append(ev)
    kinds = [e["event"] for e in events]
    assert "verdict" in kinds
    verdict = next(e for e in events if e["event"] == "verdict")
    assert verdict["data"]["red_line"] is True
    assert events[-1]["event"] == "battle_done"
    assert events[-1]["data"]["aborted"] is True

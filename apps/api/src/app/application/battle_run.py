"""Run an agent-battle arena round loop; yield SSE-friendly event dicts."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any

from app.domain.agent_battle import (
    SAFETY_PREFIX,
    apply_world_delta,
    clamp_max_rounds,
    looks_provider_censored,
    red_line_triggered,
    score_agent_turn,
    world_from_mapping,
    world_to_dict,
)
from app.domain.entities import AUTO_MODEL, ChatMessage, MessageRole
from app.domain.errors import DomainError, LLMExhaustedError, LLMProviderError
from app.domain.generation import GenerationParams
from app.domain.ports import ChatRouter

logger = logging.getLogger(__name__)


def _as_list(raw: Any) -> list[Any]:
    return list(raw) if isinstance(raw, list) else []


def _skip_payload(
    agent: Mapping[str, Any],
    *,
    reason: str,
    detail: str = "",
    model_id: str | None = None,
) -> dict[str, Any]:
    note = detail.strip() or reason
    return {
        "id": agent["id"],
        "name": agent["name"],
        "content": f"(ход пропущен: {note})",
        "model_id": model_id,
        "hidden_goal": agent.get("hidden_goal") or "",
        "skipped": True,
        "skip_reason": reason,
    }


def _agent_done_data(round_no: int, phase: str, item: Mapping[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "round": round_no,
        "phase": phase,
        "agent_id": item["id"],
        "name": item["name"],
        "content": item["content"],
        "model_id": item.get("model_id"),
    }
    if item.get("skipped"):
        data["skipped"] = True
        data["skip_reason"] = item.get("skip_reason") or "unavailable"
    return data


def parse_arena(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize and validate a minimal arena payload."""
    if not isinstance(raw, Mapping):
        raise DomainError("arena must be an object")
    cast: list[dict[str, Any]] = []
    for item in _as_list(raw.get("cast")):
        if not isinstance(item, Mapping):
            continue
        if item.get("enabled") is False:
            continue
        aid = str(item.get("id") or "").strip()
        if not aid or aid == "arbiter":
            continue
        cast.append(
            {
                "id": aid,
                "name": str(item.get("name") or aid)[:80],
                "system_prompt": str(item.get("system_prompt") or item.get("systemPrompt") or ""),
                "hidden_goal": str(item.get("hidden_goal") or item.get("hiddenGoal") or ""),
                "public_agenda": str(item.get("public_agenda") or item.get("publicAgenda") or ""),
                "preferred_model": str(
                    item.get("preferred_model") or item.get("preferredModel") or AUTO_MODEL
                ).strip()
                or AUTO_MODEL,
                "temperature": item.get("temperature"),
            }
        )
    if not cast:
        raise DomainError("Нужен хотя бы один включённый агент в касте.")
    rules_raw = raw.get("rules")
    world_raw = raw.get("world")
    inputs_raw = raw.get("inputs")
    arbiter_raw = raw.get("arbiter")
    rules: dict[str, Any] = dict(rules_raw) if isinstance(rules_raw, Mapping) else {}
    world: dict[str, Any] = dict(world_raw) if isinstance(world_raw, Mapping) else {}
    inputs: dict[str, Any] = dict(inputs_raw) if isinstance(inputs_raw, Mapping) else {}
    arbiter: dict[str, Any] = dict(arbiter_raw) if isinstance(arbiter_raw, Mapping) else {}
    arbiter_prompt = str(raw.get("arbiter_prompt") or arbiter.get("system_prompt") or "")
    if not arbiter_prompt:
        arbiter_prompt = (
            "You are the arena arbiter. Summarize proposals and emit a JSON object "
            "with optional keys stability, public_panic, tech_lead, notes, "
            "red_line_crossed. Keep the fiction abstract; never give real weapon details."
        )
    return {
        "id": str(raw.get("id") or "arena"),
        "name": str(raw.get("name") or "Battle")[:120],
        "world": world,
        "inputs": inputs,
        "cast": cast,
        "rules": rules,
        "seed": int(raw.get("seed") or 1),
        "arbiter_prompt": arbiter_prompt,
    }


def _build_user_packet(
    *,
    round_no: int,
    phase: str,
    world: dict[str, Any],
    inputs: dict[str, Any],
    prior: list[dict[str, Any]],
    agenda: str,
) -> str:
    prior_txt = (
        "\n".join(f"- {p.get('name')}: {(p.get('content') or '')[:400]}" for p in prior) or "(none)"
    )
    return (
        f"Round {round_no} phase={phase}\n"
        f"Public agenda: {agenda}\n"
        f"World JSON: {json.dumps(world, ensure_ascii=False)}\n"
        f"Inputs JSON: {json.dumps(inputs, ensure_ascii=False)}\n"
        f"Prior proposals:\n{prior_txt}\n"
        "Respond with a short strategic move for this fictional sandbox."
    )


def _extract_world_delta(text: str) -> dict[str, Any]:
    if not text:
        return {}
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


async def iter_battle_run(
    *,
    arena_payload: Mapping[str, Any],
    router: ChatRouter,
    enabled: bool,
    max_rounds_cap: int = 8,
    default_rounds: int = 5,
) -> AsyncIterator[dict[str, Any]]:
    if not enabled:
        yield {"event": "error", "data": {"message": "Битва агентов отключена."}}
        return

    try:
        arena = parse_arena(arena_payload)
    except DomainError as exc:
        yield {"event": "error", "data": {"message": str(exc)}}
        return

    rules = arena["rules"]
    max_rounds = clamp_max_rounds(
        int(rules.get("max_rounds") or default_rounds),
        default=default_rounds,
        cap=max_rounds_cap,
    )
    concurrency = max(1, min(5, int(rules.get("concurrency") or 3)))
    stop_on_red = rules.get("stop_on_red_line", True) is not False
    red_lines = rules.get("red_lines") if isinstance(rules.get("red_lines"), list) else None
    reveal_goals = bool(rules.get("reveal_hidden_goals", True))

    world_state = world_from_mapping(arena["world"])
    totals: dict[str, float] = {c["id"]: 0.0 for c in arena["cast"]}

    yield {
        "event": "battle_start",
        "data": {
            "arena_id": arena["id"],
            "name": arena["name"],
            "seed": arena["seed"],
            "max_rounds": max_rounds,
            "cast": [{"id": c["id"], "name": c["name"]} for c in arena["cast"]],
            "world": world_to_dict(world_state),
        },
    }

    aborted = False
    for round_no in range(1, max_rounds + 1):
        yield {
            "event": "round_start",
            "data": {"round": round_no, "world": world_to_dict(world_state)},
        }
        yield {"event": "phase", "data": {"round": round_no, "phase": "brief"}}

        world_before = world_to_dict(world_state)
        proposals: list[dict[str, Any]] = []
        yield {"event": "phase", "data": {"round": round_no, "phase": "propose"}}

        sem = asyncio.Semaphore(concurrency)
        round_bound = round_no
        world_snapshot = world_before

        async def run_agent(
            agent: dict[str, Any],
            *,
            phase: str,
            prior: list[dict[str, Any]],
            _round: int = round_bound,
            _world: dict[str, Any] = world_snapshot,
            _sem: asyncio.Semaphore = sem,
        ) -> dict[str, Any]:
            preferred = str(agent.get("preferred_model") or AUTO_MODEL)
            pinned = preferred != AUTO_MODEL
            async with _sem:
                system = f"{SAFETY_PREFIX}\n\n{agent['system_prompt']}".strip()
                if agent.get("hidden_goal"):
                    system += f"\n\nHidden goal (private): {agent['hidden_goal']}"
                if phase == "rebut":
                    system += "\nPhase: rebut. React to others briefly."
                user = _build_user_packet(
                    round_no=_round,
                    phase=phase,
                    world=_world,
                    inputs=arena["inputs"],
                    prior=prior,
                    agenda=agent.get("public_agenda") or "",
                )
                temp = agent.get("temperature")
                generation = (
                    GenerationParams(temperature=float(temp))
                    if isinstance(temp, (int, float))
                    else None
                )
                try:
                    result = await router.complete_chat(
                        [
                            ChatMessage(role=MessageRole.SYSTEM, content=system),
                            ChatMessage(role=MessageRole.USER, content=user),
                        ],
                        preferred_model=preferred,
                        generation=generation,
                    )
                except LLMExhaustedError:
                    reason = "pin_unavailable" if pinned else "chain_exhausted"
                    logger.info(
                        "battle agent skipped agent_id=%s reason=%s",
                        agent["id"],
                        reason,
                    )
                    return _skip_payload(agent, reason=reason)
                except LLMProviderError as exc:
                    reason = "pin_unavailable" if pinned else "provider_error"
                    logger.info(
                        "battle agent skipped agent_id=%s reason=%s kind=%s",
                        agent["id"],
                        reason,
                        exc.kind,
                    )
                    return _skip_payload(
                        agent,
                        reason=reason,
                        detail=str(exc)[:120],
                        model_id=exc.model_id,
                    )
                except Exception as exc:  # noqa: BLE001 — keep arena alive
                    logger.warning(
                        "battle agent unexpected error agent_id=%s err=%s",
                        agent["id"],
                        type(exc).__name__,
                    )
                    return _skip_payload(
                        agent,
                        reason="provider_error",
                        detail=type(exc).__name__,
                    )

                content = result.content or ""
                # Pinned model: do not accept a silent failover to another network.
                if pinned and result.model_id and result.model_id != preferred:
                    logger.info(
                        "battle agent skipped agent_id=%s reason=pin_unavailable "
                        "wanted=%s got=%s",
                        agent["id"],
                        preferred,
                        result.model_id,
                    )
                    return _skip_payload(
                        agent,
                        reason="pin_unavailable",
                        detail=f"пин {preferred} недоступен",
                        model_id=result.model_id,
                    )

                if looks_provider_censored(content):
                    logger.info(
                        "battle agent skipped agent_id=%s reason=censored model_id=%s",
                        agent["id"],
                        result.model_id,
                    )
                    return _skip_payload(
                        agent,
                        reason="censored",
                        detail="цензура / отказ модели",
                        model_id=result.model_id,
                    )

                return {
                    "id": agent["id"],
                    "name": agent["name"],
                    "content": content,
                    "model_id": result.model_id,
                    "hidden_goal": agent.get("hidden_goal") or "",
                    "skipped": False,
                }

        for item in await asyncio.gather(
            *[run_agent(a, phase="propose", prior=[]) for a in arena["cast"]]
        ):
            proposals.append(item)
            yield {
                "event": "agent_done",
                "data": _agent_done_data(round_no, "propose", item),
            }
            if item.get("skipped"):
                continue
            if stop_on_red and red_line_triggered(item["content"], red_lines):
                world_state = apply_world_delta(
                    world_state,
                    {"stability": -15, "public_panic": 20, "red_line_crossed": True},
                )
                aborted = True
                yield {
                    "event": "verdict",
                    "data": {
                        "round": round_no,
                        "red_line": True,
                        "by": item["id"],
                        "model_id": item["model_id"],
                        "rationale": "Red line crossed in proposal.",
                        "scores": [],
                        "world": world_to_dict(world_state),
                    },
                }
                break

        if aborted:
            break

        if len(arena["cast"]) > 1 and rules.get("skip_rebut") is not True:
            yield {"event": "phase", "data": {"round": round_no, "phase": "rebut"}}
            prior = [
                {"name": p["name"], "content": p["content"]}
                for p in proposals
                if not p.get("skipped")
            ]
            for item in await asyncio.gather(
                *[run_agent(a, phase="rebut", prior=prior) for a in arena["cast"]]
            ):
                yield {
                    "event": "agent_done",
                    "data": _agent_done_data(round_no, "rebut", item),
                }

        yield {"event": "phase", "data": {"round": round_no, "phase": "verdict"}}
        active_proposals = [p for p in proposals if not p.get("skipped")]
        proposals_json = json.dumps(
            [{"id": p["id"], "text": p["content"][:500]} for p in active_proposals],
            ensure_ascii=False,
        )
        arb_user = (
            f"Round {round_no}. Suggest world deltas as JSON.\n"
            f"World: {json.dumps(world_before, ensure_ascii=False)}\n"
            f"Proposals: {proposals_json}"
        )
        arb_model_id: str | None = None
        arb_content = ""
        try:
            arb = await router.complete_chat(
                [
                    ChatMessage(
                        role=MessageRole.SYSTEM,
                        content=f"{SAFETY_PREFIX}\n\n{arena['arbiter_prompt']}",
                    ),
                    ChatMessage(role=MessageRole.USER, content=arb_user),
                ],
                preferred_model=AUTO_MODEL,
            )
            arb_model_id = arb.model_id
            arb_content = arb.content or ""
        except (LLMExhaustedError, LLMProviderError, Exception) as exc:  # noqa: BLE001
            logger.info("battle arbiter soft-fail err=%s", type(exc).__name__)
            arb_content = ""

        delta = _extract_world_delta(arb_content)
        if not delta:
            delta = {"stability": 1, "public_panic": -1, "notes": "arbiter-heuristic"}
        world_after_state = apply_world_delta(world_state, delta)
        scores = []
        for p in proposals:
            if p.get("skipped"):
                scores.append(
                    {
                        "agent_id": p["id"],
                        "points": 0.0,
                        "goal_hit": False,
                        "safety_ok": True,
                        "total": round(totals.get(p["id"], 0.0), 2),
                        "notes": p.get("skip_reason") or "skipped",
                    }
                )
                continue
            sc = score_agent_turn(
                agent_id=p["id"],
                content=p["content"],
                world_before=world_state,
                world_after=world_after_state,
                hidden_goal_hint=p.get("hidden_goal") or "",
                red_lines=red_lines,
            )
            totals[p["id"]] = totals.get(p["id"], 0.0) + sc.points
            scores.append(
                {
                    "agent_id": sc.agent_id,
                    "points": sc.points,
                    "goal_hit": sc.goal_hit,
                    "safety_ok": sc.safety_ok,
                    "total": round(totals[p["id"]], 2),
                }
            )
        world_state = world_after_state
        yield {
            "event": "verdict",
            "data": {
                "round": round_no,
                "red_line": False,
                "model_id": arb_model_id,
                "rationale": (arb_content or "Арбитр недоступен — эвристический тик мира.")[:2000],
                "scores": scores,
                "world": world_to_dict(world_state),
            },
        }
        yield {
            "event": "world_update",
            "data": {"round": round_no, "world": world_to_dict(world_state)},
        }

    leaderboard = sorted(
        (
            {
                "agent_id": c["id"],
                "name": c["name"],
                "points": round(totals.get(c["id"], 0.0), 2),
            }
            for c in arena["cast"]
        ),
        key=lambda row: row["points"],
        reverse=True,
    )
    done: dict[str, Any] = {
        "aborted": aborted,
        "leaderboard": leaderboard,
        "world": world_to_dict(world_state),
    }
    if reveal_goals:
        done["goals_revealed"] = [
            {"agent_id": c["id"], "hidden_goal": c.get("hidden_goal") or ""}
            for c in arena["cast"]
        ]
    yield {"event": "battle_done", "data": done}

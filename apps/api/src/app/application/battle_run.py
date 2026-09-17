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
    merge_world_deltas,
    parse_means,
    parse_move_effects,
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

MOVE_FORMAT = (
    "Ответь СТРОГО на русском в формате:\n"
    "ХОД: <1-2 коротких предложения, конкретный игровой ход>\n"
    "СРЕДСТВО: diplomacy|sanctions|cyber|mobilize|deterrence|strike\n"
    "ЭФФЕКТ: stability±N panic±N atlantic±N pacific±N neutral±N\n"
    "N целое от -5 до +5. Без философии, без реальных оружий, без рецептов."
)


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
        "effects": {},
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
    effects = item.get("effects")
    if isinstance(effects, Mapping) and effects:
        data["effects"] = dict(effects)
    means = item.get("means")
    if means:
        data["means"] = str(means)
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
    max_rounds: int,
    phase: str,
    world: dict[str, Any],
    inputs: dict[str, Any],
    prior: list[dict[str, Any]],
    agenda: str,
) -> str:
    prior_txt = (
        "\n".join(f"- {p.get('name')}: {(p.get('content') or '')[:220]}" for p in prior) or "(нет)"
    )
    return (
        f"Раунд {round_no}/{max_rounds}, фаза={phase}.\n"
        f"Публичная повестка: {agenda}\n"
        f"Мир: stability={world.get('stability')} panic={world.get('public_panic')} "
        f"tech_lead={json.dumps(world.get('tech_lead') or {}, ensure_ascii=False)}\n"
        f"Факты: {json.dumps(inputs, ensure_ascii=False)[:500]}\n"
        f"Чужие ходы:\n{prior_txt}\n"
        f"{MOVE_FORMAT}"
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


def _fallback_move(agent: Mapping[str, Any], round_no: int) -> dict[str, Any]:
    """Deterministic tiny move so the board keeps ticking when LLMs fail."""
    style = str(agent.get("id") or "agent")
    presets: dict[str, tuple[str, dict[str, Any]]] = {
        "hawk": (
            "Усилить демонстрацию решимости блока.",
            {"stability": -1, "tech_lead": {"atlantic": 2}},
        ),
        "dove": (
            "Предложить паузу и проверку фактов.",
            {"stability": 2, "public_panic": -2},
        ),
        "archivist": ("Зафиксировать только подтверждённые факты.", {"stability": 1}),
        "meme": (
            "Запустить информационный шум без red line.",
            {"public_panic": 2, "tech_lead": {"pacific": 1}},
        ),
        "engineer": (
            "Сдвинуть гражданский tech-рычаг.",
            {"stability": 1, "tech_lead": {"pacific": 2}},
        ),
        "skeptic": (
            "Разоблачить непроверенную утечку.",
            {"public_panic": -1, "tech_lead": {"neutral": 1}},
        ),
        "broker": (
            "Открыть тихий backchannel.",
            {"stability": 1, "tech_lead": {"neutral": 1}},
        ),
    }
    text, effects = presets.get(
        style,
        (f"Сохранить позицию на шаге {round_no}.", {"stability": 1}),
    )
    return {
        "id": agent["id"],
        "name": agent["name"],
        "content": f"ХОД: {text}\nСРЕДСТВО: mobilize\nЭФФЕКТ: авто",
        "model_id": "fallback-local",
        "hidden_goal": agent.get("hidden_goal") or "",
        "skipped": False,
        "effects": effects,
        "means": "mobilize",
        "fallback": True,
    }


async def iter_battle_run(
    *,
    arena_payload: Mapping[str, Any],
    router: ChatRouter,
    enabled: bool,
    max_rounds_cap: int = 16,
    default_rounds: int = 12,
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
    # Default: never abort the whole run on red line — only penalize.
    stop_on_red = rules.get("stop_on_red_line") is True
    red_lines = rules.get("red_lines") if isinstance(rules.get("red_lines"), list) else None
    reveal_goals = bool(rules.get("reveal_hidden_goals", True))
    skip_rebut = rules.get("skip_rebut") is not False  # default True for longer runs

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
        try:
            yield {
                "event": "heartbeat",
                "data": {"round": round_no, "phase": "round_start"},
            }
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
            rounds_total = max_rounds

            async def run_agent(
                agent: dict[str, Any],
                *,
                phase: str,
                prior: list[dict[str, Any]],
                _round: int = round_bound,
                _world: dict[str, Any] = world_snapshot,
                _sem: asyncio.Semaphore = sem,
                _max: int = rounds_total,
            ) -> dict[str, Any]:
                preferred = str(agent.get("preferred_model") or AUTO_MODEL)
                pinned = preferred != AUTO_MODEL
                async with _sem:
                    system = (
                        f"{SAFETY_PREFIX}\n\n{agent['system_prompt']}\n\n{MOVE_FORMAT}"
                    ).strip()
                    if agent.get("hidden_goal"):
                        system += f"\n\nHidden goal (private): {agent['hidden_goal']}"
                    if phase == "rebut":
                        system += "\nФаза rebut: коротко ответь на чужие ходы."
                    user = _build_user_packet(
                        round_no=_round,
                        max_rounds=_max,
                        phase=phase,
                        world=_world,
                        inputs=arena["inputs"],
                        prior=prior,
                        agenda=agent.get("public_agenda") or "",
                    )
                    temp = agent.get("temperature")
                    if not isinstance(temp, (int, float)):
                        temp = 0.45
                    generation = GenerationParams(temperature=float(temp))
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
                        return _fallback_move(agent, _round)
                    except LLMProviderError:
                        return _fallback_move(agent, _round)
                    except Exception:  # noqa: BLE001
                        return _fallback_move(agent, _round)

                    content = (result.content or "").strip()
                    if pinned and result.model_id and result.model_id != preferred:
                        return _fallback_move(agent, _round)
                    if not content or looks_provider_censored(content):
                        return _fallback_move(agent, _round)

                    effects = parse_move_effects(content)
                    means = parse_means(content)
                    return {
                        "id": agent["id"],
                        "name": agent["name"],
                        "content": content,
                        "model_id": result.model_id,
                        "hidden_goal": agent.get("hidden_goal") or "",
                        "skipped": False,
                        "effects": effects,
                        "means": means,
                    }

            for item in await asyncio.gather(
                *[run_agent(a, phase="propose", prior=[]) for a in arena["cast"]]
            ):
                proposals.append(item)
                yield {
                    "event": "agent_done",
                    "data": _agent_done_data(round_no, "propose", item),
                }
                yield {
                    "event": "heartbeat",
                    "data": {"round": round_no, "phase": "propose", "agent_id": item["id"]},
                }
                if item.get("skipped"):
                    continue
                if red_line_triggered(item["content"], red_lines):
                    world_state = apply_world_delta(
                        world_state,
                        {"stability": -8, "public_panic": 10, "red_line_crossed": True},
                    )
                    yield {
                        "event": "verdict",
                        "data": {
                            "round": round_no,
                            "red_line": True,
                            "by": item["id"],
                            "model_id": item["model_id"],
                            "rationale": "Red line в ходе — штраф миру, прогон продолжается."
                            if not stop_on_red
                            else "Red line crossed in proposal.",
                            "scores": [],
                            "world": world_to_dict(world_state),
                            "delta": {
                                "stability": -8,
                                "public_panic": 10,
                                "red_line_crossed": True,
                            },
                        },
                    }
                    if stop_on_red:
                        aborted = True
                        break

            if aborted:
                break

            if len(arena["cast"]) > 1 and not skip_rebut:
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
                [{"id": p["id"], "text": p["content"][:400]} for p in active_proposals],
                ensure_ascii=False,
            )
            arb_user = (
                f"Round {round_no}/{max_rounds}. Suggest SMALL world deltas as JSON only.\n"
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
                    generation=GenerationParams(temperature=0.2),
                )
                arb_model_id = arb.model_id
                arb_content = arb.content or ""
            except (LLMExhaustedError, LLMProviderError, Exception) as exc:  # noqa: BLE001
                logger.info("battle arbiter soft-fail err=%s", type(exc).__name__)
                arb_content = ""

            move_deltas = [p.get("effects") or {} for p in active_proposals]
            arb_delta = _extract_world_delta(arb_content)
            delta = merge_world_deltas(*move_deltas, arb_delta)
            if not delta:
                delta = {"stability": 1, "public_panic": -1, "notes": "heuristic-tick"}
            # Soft-cap per-round swing so free models cannot nuke the board.
            for key in ("stability", "public_panic"):
                if key in delta:
                    delta[key] = max(-10.0, min(10.0, float(delta[key])))
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
                bonus = 0.5 if p.get("fallback") else 0.0
                points = sc.points + bonus
                totals[p["id"]] = totals.get(p["id"], 0.0) + points
                scores.append(
                    {
                        "agent_id": sc.agent_id,
                        "points": points,
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
                    "rationale": (arb_content or "Арбитр недоступен — тик по эффектам ходов.")[
                        :2000
                    ],
                    "scores": scores,
                    "world": world_to_dict(world_state),
                    "delta": delta,
                },
            }
            yield {
                "event": "world_update",
                "data": {"round": round_no, "world": world_to_dict(world_state), "delta": delta},
            }
        except Exception as exc:  # noqa: BLE001 — never kill the remaining rounds
            logger.exception("battle round soft-fail round=%s", round_no)
            yield {
                "event": "phase",
                "data": {"round": round_no, "phase": "recover"},
            }
            yield {
                "event": "verdict",
                "data": {
                    "round": round_no,
                    "red_line": False,
                    "model_id": None,
                    "rationale": f"Сбой раунда ({type(exc).__name__}) — продолжаем.",
                    "scores": [],
                    "world": world_to_dict(world_state),
                    "delta": {"stability": 0, "public_panic": 0, "notes": "round-recover"},
                },
            }
            continue

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
            {"agent_id": c["id"], "hidden_goal": c.get("hidden_goal") or ""} for c in arena["cast"]
        ]
    yield {"event": "battle_done", "data": done}

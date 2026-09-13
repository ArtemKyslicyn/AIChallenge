"""Execute an agent graph (DAG) with handoff between nodes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.application.agent_run import run_agent
from app.domain.agent_definition import AgentDefinition
from app.domain.agent_graph import GraphNode, GraphPlan, parse_graph_payload, plan_graph
from app.domain.entities import AUTO_MODEL
from app.domain.generation import GenerationParams
from app.domain.ports import ChatRouter


@dataclass(frozen=True, slots=True)
class GraphNodeResult:
    node_id: str
    kind: str
    label: str
    content: str
    model_id: str | None


async def iter_graph_run(
    *,
    graph_payload: dict[str, Any],
    message: str,
    router: ChatRouter,
    enabled: bool,
    max_message_chars: int,
) -> AsyncIterator[dict[str, Any]]:
    """Yield SSE-friendly event dicts: node_start, node_end, done, error."""
    graph = parse_graph_payload(graph_payload)
    plan = plan_graph(graph)
    by_id = {n.id: n for n in graph.nodes}
    outputs: dict[str, str] = {}
    user = (message or "").strip()
    if not user:
        yield {"event": "error", "data": {"message": "Пустое входное сообщение."}}
        return

    yield {
        "event": "graph_start",
        "data": {
            "name": graph.name,
            "order": list(plan.order),
            "start_id": plan.start_id,
        },
    }

    for nid in plan.order:
        node = by_id[nid]
        yield {
            "event": "node_start",
            "data": {"node_id": nid, "kind": node.kind, "label": node.label},
        }
        try:
            result = await _run_node(
                node=node,
                plan=plan,
                by_id=by_id,
                outputs=outputs,
                user_message=user,
                router=router,
                enabled=enabled,
                max_message_chars=max_message_chars,
            )
        except Exception as exc:  # noqa: BLE001 — surface to SSE
            yield {
                "event": "error",
                "data": {"node_id": nid, "message": str(exc)[:500]},
            }
            return
        outputs[nid] = result.content
        yield {
            "event": "node_end",
            "data": {
                "node_id": nid,
                "kind": node.kind,
                "label": node.label,
                "content": result.content,
                "model_id": result.model_id,
            },
        }

    final_parts = [outputs[eid] for eid in plan.end_ids if eid in outputs]
    yield {
        "event": "done",
        "data": {
            "content": "\n\n".join(final_parts).strip(),
            "end_ids": list(plan.end_ids),
        },
    }


async def _run_node(
    *,
    node: GraphNode,
    plan: GraphPlan,
    by_id: dict[str, GraphNode],
    outputs: dict[str, str],
    user_message: str,
    router: ChatRouter,
    enabled: bool,
    max_message_chars: int,
) -> GraphNodeResult:
    preds = plan.predecessors.get(node.id, ())

    if node.kind == "start":
        return GraphNodeResult(
            node_id=node.id,
            kind=node.kind,
            label=node.label,
            content=user_message,
            model_id=None,
        )

    if node.kind == "end":
        # Pass through first predecessor (or join)
        parts = [outputs[p] for p in preds if p in outputs]
        text = "\n\n".join(parts).strip() or user_message
        return GraphNodeResult(
            node_id=node.id,
            kind=node.kind,
            label=node.label,
            content=text,
            model_id=None,
        )

    if node.kind == "merge":
        blocks: list[str] = []
        for p in preds:
            src = by_id.get(p)
            label = (src.label if src else p) or p
            if p in outputs:
                blocks.append(f"### {label}\n{outputs[p]}")
        merged = "\n\n".join(blocks).strip() or user_message
        # Optional LLM glue if merge has a system prompt
        if (node.system_prompt or "").strip():
            definition = AgentDefinition(
                name=node.label or "Merge",
                system_prompt=node.system_prompt.strip(),
                preferred_model=node.preferred_model or AUTO_MODEL,
                temperature=node.temperature,
                max_tokens=node.max_tokens,
            )
            gen = GenerationParams(
                temperature=node.temperature,
                max_tokens=node.max_tokens,
            )
            outcome = await run_agent(
                definition=definition,
                message=f"Объедини ответы:\n\n{merged}",
                router=router,
                enabled=enabled,
                max_message_chars=max_message_chars,
                generation=gen,
            )
            return GraphNodeResult(
                node_id=node.id,
                kind=node.kind,
                label=node.label,
                content=outcome.result.content,
                model_id=outcome.result.model_id,
            )
        return GraphNodeResult(
            node_id=node.id,
            kind=node.kind,
            label=node.label,
            content=merged,
            model_id=None,
        )

    # agent
    incoming = [outputs[p] for p in preds if p in outputs]
    if not incoming:
        prompt = user_message
    elif len(incoming) == 1:
        pred = by_id.get(preds[0]) if preds else None
        if pred and pred.kind == "start":
            prompt = user_message
        else:
            prompt = (
                f"Вход пользователя:\n{user_message}\n\n"
                f"Ответ предыдущего шага:\n{incoming[0]}\n\n"
                "Продолжи задачу."
            )
    else:
        joined = "\n\n".join(incoming)
        prompt = (
            f"Вход пользователя:\n{user_message}\n\n"
            f"Контекст от предыдущих узлов:\n{joined}\n\n"
            "Собери ответ."
        )

    system = (node.system_prompt or "").strip() or "Ты полезный агент. Отвечай кратко."
    definition = AgentDefinition(
        name=node.label or "Agent",
        system_prompt=system,
        preferred_model=node.preferred_model or AUTO_MODEL,
        temperature=node.temperature,
        max_tokens=node.max_tokens,
    )
    gen = GenerationParams(temperature=node.temperature, max_tokens=node.max_tokens)
    outcome = await run_agent(
        definition=definition,
        message=prompt,
        router=router,
        enabled=enabled,
        max_message_chars=max_message_chars,
        generation=gen,
    )
    return GraphNodeResult(
        node_id=node.id,
        kind=node.kind,
        label=node.label,
        content=outcome.result.content,
        model_id=outcome.result.model_id,
    )


# re-export for tests
__all__ = ["GraphNodeResult", "iter_graph_run", "parse_graph_payload", "plan_graph", "AgentGraph"]

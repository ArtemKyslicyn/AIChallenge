"""Agent graph domain: validate DAG and plan execution order."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.domain.errors import MessageValidationError

GraphNodeKind = Literal["start", "agent", "merge", "end"]


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: str
    kind: GraphNodeKind
    label: str = ""
    system_prompt: str = ""
    preferred_model: str = "auto"
    temperature: float | None = 0.3
    max_tokens: int | None = 512


@dataclass(frozen=True, slots=True)
class GraphEdge:
    id: str
    source: str
    target: str


@dataclass(frozen=True, slots=True)
class AgentGraph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    name: str = ""


@dataclass(frozen=True, slots=True)
class GraphPlan:
    order: tuple[str, ...]  # node ids in execution order
    start_id: str
    end_ids: tuple[str, ...]
    predecessors: dict[str, tuple[str, ...]] = field(default_factory=dict)
    successors: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _kind(raw: Any) -> GraphNodeKind:
    k = str(raw or "").strip().lower()
    if k not in ("start", "agent", "merge", "end"):
        raise MessageValidationError(f"Неизвестный тип узла: {raw!r}")
    return k  # type: ignore[return-value]


def parse_graph_payload(raw: dict[str, Any]) -> AgentGraph:
    nodes_raw = raw.get("nodes") or []
    edges_raw = raw.get("edges") or []
    if not isinstance(nodes_raw, list) or not isinstance(edges_raw, list):
        raise MessageValidationError("nodes и edges должны быть списками.")
    nodes: list[GraphNode] = []
    seen: set[str] = set()
    for item in nodes_raw:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("id") or "").strip()
        if not nid:
            raise MessageValidationError("У узла нет id.")
        if nid in seen:
            raise MessageValidationError(f"Дубликат id узла: {nid}")
        seen.add(nid)
        data = item.get("data") if isinstance(item.get("data"), dict) else item
        kind = _kind(data.get("kind") or item.get("type"))
        nodes.append(
            GraphNode(
                id=nid,
                kind=kind,
                label=str(data.get("label") or "")[:120],
                system_prompt=str(data.get("systemPrompt") or data.get("system_prompt") or ""),
                preferred_model=str(
                    data.get("preferredModel") or data.get("preferred_model") or "auto"
                ).strip()
                or "auto",
                temperature=data.get("temperature")
                if isinstance(data.get("temperature"), (int, float))
                else 0.3,
                max_tokens=int(data["max_tokens"])
                if isinstance(data.get("max_tokens"), int)
                else (
                    int(data["maxTokens"])
                    if isinstance(data.get("maxTokens"), int)
                    else 512
                ),
            )
        )
    edges: list[GraphEdge] = []
    for i, item in enumerate(edges_raw):
        if not isinstance(item, dict):
            continue
        src = str(item.get("source") or "").strip()
        tgt = str(item.get("target") or "").strip()
        if not src or not tgt:
            raise MessageValidationError("Ребро без source/target.")
        if src not in seen or tgt not in seen:
            raise MessageValidationError(f"Ребро ссылается на неизвестный узел: {src}→{tgt}")
        eid = str(item.get("id") or f"e{i}")
        edges.append(GraphEdge(id=eid, source=src, target=tgt))
    if not nodes:
        raise MessageValidationError("Схема пуста.")
    return AgentGraph(
        nodes=tuple(nodes),
        edges=tuple(edges),
        name=str(raw.get("name") or "")[:120],
    )


def plan_graph(graph: AgentGraph) -> GraphPlan:
    by_id = {n.id: n for n in graph.nodes}
    starts = [n for n in graph.nodes if n.kind == "start"]
    ends = [n for n in graph.nodes if n.kind == "end"]
    if len(starts) != 1:
        raise MessageValidationError("В схеме должен быть ровно один узел Старт.")
    if not ends:
        raise MessageValidationError("В схеме нужен хотя бы один узел Конец.")

    preds: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
    succs: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
    for e in graph.edges:
        if e.target == starts[0].id:
            raise MessageValidationError("У Старта не должно быть входящих связей.")
        if e.source in {x.id for x in ends}:
            raise MessageValidationError("У Конца не должно быть исходящих связей.")
        preds[e.target].append(e.source)
        succs[e.source].append(e.target)

    # Kahn topological sort; must include only nodes reachable from start
    reachable: set[str] = set()
    stack = [starts[0].id]
    while stack:
        cur = stack.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        stack.extend(succs[cur])

    indeg = {nid: 0 for nid in reachable}
    for nid in reachable:
        for p in preds[nid]:
            if p in reachable:
                indeg[nid] += 1

    queue = [nid for nid, d in indeg.items() if d == 0]
    order: list[str] = []
    while queue:
        # stable-ish: prefer start first then agents
        queue.sort(key=lambda i: (0 if by_id[i].kind == "start" else 1, i))
        nid = queue.pop(0)
        order.append(nid)
        for s in succs[nid]:
            if s not in indeg:
                continue
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)

    if len(order) != len(reachable):
        raise MessageValidationError("В схеме есть цикл — пока поддерживаются только DAG.")

    # Every agent/merge must be reachable
    for n in graph.nodes:
        if n.kind in ("agent", "merge") and n.id not in reachable:
            raise MessageValidationError(f"Узел «{n.label or n.id}» недостижим от Старта.")

    return GraphPlan(
        order=tuple(order),
        start_id=starts[0].id,
        end_ids=tuple(e.id for e in ends if e.id in reachable),
        predecessors={k: tuple(v) for k, v in preds.items()},
        successors={k: tuple(v) for k, v in succs.items()},
    )

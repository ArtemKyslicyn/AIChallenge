import {
  Background,
  ConnectionMode,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type OnConnect,
  type ReactFlowInstance,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import "@xyflow/react/dist/style.css";

import {
  ApiError,
  runAgentGraphSSE,
  type AgentGraphRunEvent,
} from "../api/client";
import { emptyGraph, loadGraph, saveGraph } from "../studio/persist";
import { GRAPH_TEMPLATES } from "../studio/templates";
import {
  NODE_KIND_LABEL,
  PALETTE,
  type AgentNodeData,
  type GraphNodeKind,
} from "../studio/types";
import { AgentGraphNodeView, type AgentGraphNode } from "./studio/AgentGraphNodeView";

const nodeTypes = { agentGraph: AgentGraphNodeView };

const defaultEdgeOptions = {
  type: "smoothstep" as const,
  animated: false,
  style: { strokeWidth: 2 },
  className: "ag-edge",
};

type LogLine = {
  id: string;
  kind: string;
  text: string;
  modelId?: string | null;
};

let idSeq = 0;
function nextId(prefix: string) {
  idSeq += 1;
  return `${prefix}-${Date.now().toString(36)}-${idSeq}`;
}

function AgentStudioInner() {
  const boot = useMemo(() => loadGraph(), []);
  const [name, setName] = useState(boot.name);
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentGraphNode>(
    boot.nodes as AgentGraphNode[],
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(boot.edges);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [runInput, setRunInput] = useState("Собери короткое ТЗ для чат-платформы.");
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<LogLine[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const rfRef = useRef<ReactFlowInstance<AgentGraphNode, Edge> | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const selected = useMemo(
    () => nodes.find((n) => n.id === selectedId) ?? null,
    [nodes, selectedId],
  );

  useEffect(() => {
    saveGraph({ name, nodes, edges, updatedAt: new Date().toISOString() });
  }, [name, nodes, edges]);

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      if (connection.source === connection.target) return;
      setEdges((eds) => {
        const dup = eds.some(
          (e) =>
            e.source === connection.source &&
            e.target === connection.target &&
            (e.sourceHandle || "out") === (connection.sourceHandle || "out") &&
            (e.targetHandle || "in") === (connection.targetHandle || "in"),
        );
        if (dup) return eds;
        const next = addEdge(
          {
            ...connection,
            id: nextId("e"),
            ...defaultEdgeOptions,
          },
          eds,
        );
        return next;
      });
      setStatus("Связь добавлена");
    },
    [setEdges],
  );

  const isValidConnection = useCallback(
    (connection: Connection | Edge) => {
      const sourceId = "source" in connection ? connection.source : null;
      const targetId = "target" in connection ? connection.target : null;
      if (!sourceId || !targetId || sourceId === targetId) return false;
      const src = nodes.find((n) => n.id === sourceId);
      const tgt = nodes.find((n) => n.id === targetId);
      if (!src || !tgt) return false;
      if (src.data.kind === "end") return false;
      if (tgt.data.kind === "start") return false;
      return true;
    },
    [nodes],
  );

  /** Quick-link: connect selected node → another agent/merge/end. */
  const linkSelectedTo = useCallback(
    (targetId: string) => {
      if (!selectedId || selectedId === targetId) return;
      const src = nodes.find((n) => n.id === selectedId);
      const tgt = nodes.find((n) => n.id === targetId);
      if (!src || !tgt) return;
      if (src.data.kind === "end" || tgt.data.kind === "start") {
        setStatus("Такую связь нельзя: Конец не отдаёт, Старт не принимает.");
        return;
      }
      onConnect({
        source: selectedId,
        target: targetId,
        sourceHandle: "out",
        targetHandle: "in",
      });
    },
    [nodes, onConnect, selectedId],
  );

  const addNode = useCallback(
    (kind: GraphNodeKind, position?: { x: number; y: number }) => {
      const id = nextId(kind);
      const pos =
        position ??
        ({
          x: 120 + (nodes.length % 5) * 40,
          y: 100 + nodes.length * 28,
        } as const);
      const node: AgentGraphNode = {
        id,
        type: "agentGraph",
        position: pos,
        data: {
          kind,
          label: NODE_KIND_LABEL[kind],
          preferredModel: kind === "agent" ? "auto" : undefined,
          systemPrompt: kind === "agent" ? "Ты полезный агент. Отвечай кратко." : undefined,
        },
      };
      setNodes((ns) => [...ns, node]);
      setSelectedId(id);
      setStatus(`Добавлен узел «${NODE_KIND_LABEL[kind]}»`);
    },
    [nodes.length, setNodes],
  );

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const raw = e.dataTransfer.getData("application/aichallenge-node");
      const kind = raw as GraphNodeKind;
      if (!raw || !(kind in NODE_KIND_LABEL)) return;
      const bounds = wrapRef.current?.getBoundingClientRect();
      const flow = rfRef.current;
      if (!bounds || !flow) {
        addNode(kind);
        return;
      }
      const position = flow.screenToFlowPosition({
        x: e.clientX,
        y: e.clientY,
      });
      addNode(kind, position);
    },
    [addNode],
  );

  const patchSelected = useCallback(
    (patch: Partial<AgentNodeData>) => {
      if (!selectedId) return;
      setNodes((ns) =>
        ns.map((n) =>
          n.id === selectedId ? { ...n, data: { ...n.data, ...patch } } : n,
        ),
      );
    },
    [selectedId, setNodes],
  );

  const applyTemplate = useCallback(
    (templateId: string) => {
      const t = GRAPH_TEMPLATES.find((x) => x.id === templateId);
      if (!t) return;
      const stamp = Date.now().toString(36);
      const idMap = new Map<string, string>();
      const newNodes = t.nodes.map((n) => {
        const nid = `${n.id}-${stamp}`;
        idMap.set(n.id, nid);
        return { ...n, id: nid } as AgentGraphNode;
      });
      const newEdges = t.edges.map((e) => ({
        ...e,
        id: `${e.id}-${stamp}`,
        source: idMap.get(e.source) || e.source,
        target: idMap.get(e.target) || e.target,
      }));
      setNodes(newNodes);
      setEdges(newEdges);
      setName(t.title);
      setSelectedId(null);
      setStatus(`Шаблон «${t.title}»`);
      queueMicrotask(() => rfRef.current?.fitView({ padding: 0.2 }));
    },
    [setEdges, setNodes],
  );

  const clearAll = useCallback(() => {
    const empty = emptyGraph(name || "Новая схема");
    setNodes([]);
    setEdges([]);
    setSelectedId(null);
    setName(empty.name);
    setLog([]);
    setStatus("Схема очищена");
  }, [name, setEdges, setNodes]);

  const setRunState = useCallback(
    (nodeId: string, runState: AgentNodeData["runState"]) => {
      setNodes((ns) =>
        ns.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, runState } } : n,
        ),
      );
    },
    [setNodes],
  );

  const resetRunStates = useCallback(() => {
    setNodes((ns) =>
      ns.map((n) => ({ ...n, data: { ...n.data, runState: "idle" as const } })),
    );
  }, [setNodes]);

  const stopRun = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setRunning(false);
    setStatus("Остановлено");
  }, []);

  const runGraph = useCallback(async () => {
    const msg = runInput.trim();
    if (!msg) {
      setStatus("Введите сообщение для старта.");
      return;
    }
    if (nodes.length === 0) {
      setStatus("Схема пуста — добавьте узлы или шаблон.");
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setLog([]);
    resetRunStates();
    setStatus("Запуск схемы…");

    const graph = {
      name,
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: {
          kind: n.data.kind,
          label: n.data.label,
          systemPrompt: n.data.systemPrompt,
          preferredModel: n.data.preferredModel,
        },
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle,
        targetHandle: e.targetHandle,
      })),
    };

    const pushLog = (line: LogLine) => setLog((prev) => [...prev, line]);

    try {
      await runAgentGraphSSE(
        msg,
        graph,
        (ev: AgentGraphRunEvent) => {
          if (ev.type === "graph_start") {
            setStatus(`Порядок: ${ev.order.length} узлов`);
          } else if (ev.type === "node_start") {
            setRunState(ev.node_id, "running");
            pushLog({
              id: `s-${ev.node_id}-${Date.now()}`,
              kind: "start",
              text: `→ ${ev.label || ev.kind}`,
            });
          } else if (ev.type === "node_end") {
            setRunState(ev.node_id, "done");
            pushLog({
              id: `e-${ev.node_id}-${Date.now()}`,
              kind: "end",
              text: ev.content,
              modelId: ev.model_id,
            });
          } else if (ev.type === "done") {
            setStatus("Готово");
            pushLog({
              id: `done-${Date.now()}`,
              kind: "done",
              text: ev.content || "(пусто)",
            });
          } else if (ev.type === "error") {
            if (ev.node_id) setRunState(ev.node_id, "error");
            setStatus(ev.message);
            pushLog({
              id: `err-${Date.now()}`,
              kind: "error",
              text: ev.message,
            });
          }
        },
        controller.signal,
      );
    } catch (e) {
      if (controller.signal.aborted) return;
      const message = e instanceof ApiError ? e.message : "Не удалось запустить схему.";
      setStatus(message);
      pushLog({ id: `err-${Date.now()}`, kind: "error", text: message });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setRunning(false);
    }
  }, [edges, name, nodes, resetRunStates, runInput, setRunState]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Delete" || e.key === "Backspace") {
        const tag = (e.target as HTMLElement)?.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
        setNodes((ns) => ns.filter((n) => n.id !== selectedId));
        setEdges((eds) =>
          eds.filter((ed) => ed.source !== selectedId && ed.target !== selectedId),
        );
        if (selectedId) setSelectedId(null);
      }
    },
    [selectedId, setEdges, setNodes],
  );

  const linkTargets = useMemo(() => {
    if (!selected || selected.data.kind === "end") return [];
    return nodes.filter((n) => n.id !== selected.id && n.data.kind !== "start");
  }, [nodes, selected]);

  return (
    <div className="agent-graph" onKeyDown={onKeyDown}>
      <header className="agent-graph-top">
        <div className="agent-graph-title">
          <h2>Схема Агентов</h2>
          <p className="agent-graph-sub">Потяни точку → точку или «Связать» в свойствах</p>
        </div>
        <label className="agent-graph-name">
          <span className="sr-only">Название схемы</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Название схемы"
          />
        </label>
        <div className="agent-graph-actions">
          <button type="button" className="ghost-button" onClick={clearAll} disabled={running}>
            Очистить
          </button>
          {running ? (
            <button type="button" className="ghost-button" onClick={stopRun}>
              Стоп
            </button>
          ) : (
            <button type="button" className="primary-button" onClick={() => void runGraph()}>
              Запустить
            </button>
          )}
        </div>
      </header>

      <div className="agent-graph-body">
        <aside className="agent-graph-palette" aria-label="Палитра узлов">
          <div className="agent-graph-panel-head">
            <h3>Узлы</h3>
          </div>
          <ul className="agent-graph-palette-list">
            {PALETTE.map((item) => (
              <li key={item.kind}>
                <button
                  type="button"
                  className={`ag-palette-item ag-palette-item--${item.kind}`}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("application/aichallenge-node", item.kind);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  onClick={() => addNode(item.kind)}
                  title={item.hint}
                >
                  <span className="ag-palette-dot" aria-hidden="true" />
                  <span className="ag-palette-copy">
                    <span className="ag-palette-title">{NODE_KIND_LABEL[item.kind]}</span>
                    <span className="ag-palette-hint">{item.hint}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <div className="agent-graph-panel-head">
            <h3>Шаблоны</h3>
          </div>
          <ul className="agent-graph-templates">
            {GRAPH_TEMPLATES.map((t) => (
              <li key={t.id}>
                <button type="button" className="ag-template-btn" onClick={() => applyTemplate(t.id)}>
                  <strong>{t.title}</strong>
                  <span>{t.blurb}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <div
          className="agent-graph-canvas"
          ref={wrapRef}
          onDragOver={onDragOver}
          onDrop={onDrop}
        >
          {nodes.length === 0 ? (
            <div className="agent-graph-empty">
              <div className="agent-graph-empty-card">
                <strong>Пустая схема</strong>
                <p>Перетащи узел слева или открой шаблон. Связи — от точки к точке.</p>
              </div>
            </div>
          ) : null}
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            isValidConnection={isValidConnection}
            connectionMode={ConnectionMode.Loose}
            connectionRadius={36}
            connectOnClick
            defaultEdgeOptions={defaultEdgeOptions}
            nodesConnectable
            elementsSelectable
            edgesReconnectable
            nodeTypes={nodeTypes}
            onInit={(inst) => {
              rfRef.current = inst;
            }}
            onSelectionChange={({ nodes: sel }) => {
              setSelectedId(sel[0]?.id ?? null);
            }}
            fitView
            fitViewOptions={{ padding: 0.18 }}
            deleteKeyCode={null}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={20} size={1} color="var(--ag-grid)" />
            <Controls showInteractive={false} className="agent-graph-controls" />
            <MiniMap
              pannable
              zoomable
              className="agent-graph-minimap"
              maskColor="color-mix(in srgb, var(--bg) 55%, transparent)"
            />
          </ReactFlow>
        </div>

        <aside className="agent-graph-inspector" aria-label="Свойства узла">
          <div className="agent-graph-panel-head">
            <h3>Свойства</h3>
            {selected ? (
              <span className={`ag-kind-chip ag-kind-chip--${selected.data.kind}`}>
                {NODE_KIND_LABEL[selected.data.kind]}
              </span>
            ) : null}
          </div>
          {!selected ? (
            <p className="agent-graph-muted">Выбери узел на схеме, чтобы править подпись, модель и связи.</p>
          ) : (
            <div className="agent-graph-fields">
              <label>
                <span>Подпись</span>
                <input
                  value={selected.data.label}
                  onChange={(e) => patchSelected({ label: e.target.value })}
                />
              </label>
              {selected.data.kind === "agent" ? (
                <>
                  <label>
                    <span>Модель</span>
                    <input
                      value={selected.data.preferredModel || "auto"}
                      onChange={(e) => patchSelected({ preferredModel: e.target.value })}
                      placeholder="auto"
                    />
                  </label>
                  <label className="agent-graph-field-grow">
                    <span>Инструкция</span>
                    <textarea
                      rows={5}
                      value={selected.data.systemPrompt || ""}
                      onChange={(e) => patchSelected({ systemPrompt: e.target.value })}
                    />
                  </label>
                </>
              ) : null}
              {selected.data.kind !== "end" ? (
                <div className="agent-graph-link-to">
                  <span className="agent-graph-link-label">Связать →</span>
                  {linkTargets.length === 0 ? (
                    <p className="agent-graph-muted">Добавь ещё узлы, чтобы связать.</p>
                  ) : (
                    <div className="agent-graph-link-btns">
                      {linkTargets.map((n) => (
                        <button
                          key={n.id}
                          type="button"
                          className="ag-link-chip"
                          onClick={() => linkSelectedTo(n.id)}
                        >
                          {n.data.label || NODE_KIND_LABEL[n.data.kind]}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          )}
          {status ? (
            <p className="agent-graph-status" role="status">
              {status}
            </p>
          ) : null}
          <p className="agent-graph-hint">Del — удалить узел · автосохранение в браузере</p>
        </aside>
      </div>

      <footer className="agent-graph-run">
        <label className="agent-graph-run-input">
          <span>Вход для Старта</span>
          <textarea
            rows={2}
            value={runInput}
            disabled={running}
            onChange={(e) => setRunInput(e.target.value)}
            placeholder="Сообщение для схемы…"
          />
        </label>
        <div className="agent-graph-log" aria-live="polite">
          <div className="agent-graph-log-head">Лог</div>
          {log.length === 0 ? (
            <p className="agent-graph-muted">Появится после запуска.</p>
          ) : (
            <div className="agent-graph-log-scroll">
              {log.map((line) => (
                <article
                  key={line.id}
                  className={`agent-graph-log-line agent-graph-log-line--${line.kind}`}
                >
                  {line.modelId ? <span className="badge">{line.modelId}</span> : null}
                  <p>{line.text}</p>
                </article>
              ))}
            </div>
          )}
        </div>
      </footer>
    </div>
  );
}

export function AgentStudio() {
  return (
    <ReactFlowProvider>
      <AgentStudioInner />
    </ReactFlowProvider>
  );
}

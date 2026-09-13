import {
  Background,
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
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: nextId("e"),
            animated: false,
          },
          eds,
        ),
      );
    },
    [setEdges],
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

  return (
    <div className="agent-graph" onKeyDown={onKeyDown}>
      <header className="agent-graph-top">
        <div className="agent-graph-title">
          <h2>Схема Агентов</h2>
          <p className="agent-graph-sub">
            Собери цепочку узлов и связей, затем нажми «Запустить».
          </p>
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
          <h3>Узлы</h3>
          <ul>
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
                >
                  <span className="ag-palette-title">{NODE_KIND_LABEL[item.kind]}</span>
                  <span className="ag-palette-hint">{item.hint}</span>
                </button>
              </li>
            ))}
          </ul>
          <h3>Шаблоны</h3>
          <ul className="agent-graph-templates">
            {GRAPH_TEMPLATES.map((t) => (
              <li key={t.id}>
                <button type="button" className="ghost-button" onClick={() => applyTemplate(t.id)}>
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
              <p>Перетащи узел из палитры или выбери шаблон.</p>
            </div>
          ) : null}
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            onInit={(inst) => {
              rfRef.current = inst;
            }}
            onSelectionChange={({ nodes: sel }) => {
              setSelectedId(sel[0]?.id ?? null);
            }}
            fitView
            deleteKeyCode={null}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={18} size={1} color="var(--ag-grid, #d8dde6)" />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable className="agent-graph-minimap" />
          </ReactFlow>
        </div>

        <aside className="agent-graph-inspector" aria-label="Свойства узла">
          <h3>Свойства</h3>
          {!selected ? (
            <p className="agent-graph-muted">Выбери узел на схеме.</p>
          ) : (
            <div className="agent-graph-fields">
              <label>
                <span>Тип</span>
                <input value={NODE_KIND_LABEL[selected.data.kind]} readOnly />
              </label>
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
                  <label>
                    <span>Инструкция</span>
                    <textarea
                      rows={8}
                      value={selected.data.systemPrompt || ""}
                      onChange={(e) => patchSelected({ systemPrompt: e.target.value })}
                    />
                  </label>
                </>
              ) : null}
            </div>
          )}
          {status ? (
            <p className="agent-graph-status" role="status">
              {status}
            </p>
          ) : null}
          <p className="agent-graph-hint">
            Del — удалить выбранный узел. Схема сохраняется в браузере.
          </p>
        </aside>
      </div>

      <footer className="agent-graph-run">
        <label className="agent-graph-run-input">
          <span>Вход (Старт)</span>
          <textarea
            rows={2}
            value={runInput}
            disabled={running}
            onChange={(e) => setRunInput(e.target.value)}
            placeholder="Сообщение для схемы…"
          />
        </label>
        <div className="agent-graph-log" aria-live="polite">
          {log.length === 0 ? (
            <p className="agent-graph-muted">Лог запуска появится здесь.</p>
          ) : (
            log.map((line) => (
              <article key={line.id} className={`agent-graph-log-line agent-graph-log-line--${line.kind}`}>
                {line.modelId ? <span className="badge">{line.modelId}</span> : null}
                <p>{line.text}</p>
              </article>
            ))
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

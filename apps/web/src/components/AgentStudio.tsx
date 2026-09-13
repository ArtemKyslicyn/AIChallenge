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
    setStatus("Схема очищена");
  }, [name, setEdges, setNodes]);

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
            Собери цепочку узлов и связей. Запуск графа — следующим этапом.
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
          <button type="button" className="ghost-button" onClick={clearAll}>
            Очистить
          </button>
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

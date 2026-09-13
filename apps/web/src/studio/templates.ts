/** Built-in graph templates for empty-state. */

import type { Edge, Node } from "@xyflow/react";

import type { AgentNodeData } from "./types";

function n(
  id: string,
  kind: AgentNodeData["kind"],
  label: string,
  x: number,
  y: number,
  extra?: Partial<AgentNodeData>,
): Node<AgentNodeData> {
  return {
    id,
    type: "agentGraph",
    position: { x, y },
    data: { kind, label, ...extra },
  };
}

export type GraphTemplate = {
  id: string;
  title: string;
  blurb: string;
  nodes: Node<AgentNodeData>[];
  edges: Edge[];
};

export const GRAPH_TEMPLATES: GraphTemplate[] = [
  {
    id: "chain",
    title: "Цепочка",
    blurb: "Старт → Агент A → Агент B → Конец",
    nodes: [
      n("t-start", "start", "Старт", 80, 160),
      n("t-a", "agent", "Агент A", 280, 140, {
        systemPrompt: "Ты первый агент. Кратко уточни задачу.",
      }),
      n("t-b", "agent", "Агент B", 500, 140, {
        systemPrompt: "Ты второй агент. Доработай ответ предыдущего.",
      }),
      n("t-end", "end", "Конец", 720, 160),
    ],
    edges: [
      { id: "e1", source: "t-start", target: "t-a", sourceHandle: "out", targetHandle: "in" },
      { id: "e2", source: "t-a", target: "t-b", sourceHandle: "out", targetHandle: "in" },
      { id: "e3", source: "t-b", target: "t-end", sourceHandle: "out", targetHandle: "in" },
    ],
  },
  {
    id: "parallel",
    title: "Параллель → слияние",
    blurb: "Два агента параллельно, затем Merge",
    nodes: [
      n("p-start", "start", "Старт", 60, 180),
      n("p-a", "agent", "Агент A", 280, 60, {
        systemPrompt: "Ответь с точки зрения краткости.",
      }),
      n("p-b", "agent", "Агент B", 280, 260, {
        systemPrompt: "Ответь с точки зрения полноты.",
      }),
      n("p-merge", "merge", "Слияние", 520, 160),
      n("p-end", "end", "Конец", 740, 180),
    ],
    edges: [
      { id: "pe1", source: "p-start", target: "p-a", sourceHandle: "out", targetHandle: "in" },
      { id: "pe2", source: "p-start", target: "p-b", sourceHandle: "out", targetHandle: "in" },
      { id: "pe3", source: "p-a", target: "p-merge", sourceHandle: "out", targetHandle: "in" },
      { id: "pe4", source: "p-b", target: "p-merge", sourceHandle: "out", targetHandle: "in" },
      { id: "pe5", source: "p-merge", target: "p-end", sourceHandle: "out", targetHandle: "in" },
    ],
  },
];

/** Local persistence for agent graph canvas. */

import type { Edge, Node } from "@xyflow/react";

import type { AgentNodeData } from "./types";

const KEY = "aichallenge.agent_graph.v1";

export type GraphDoc = {
  name: string;
  nodes: Node<AgentNodeData>[];
  edges: Edge[];
  updatedAt: string;
};

export function emptyGraph(name = "Новая схема"): GraphDoc {
  return {
    name,
    nodes: [],
    edges: [],
    updatedAt: new Date().toISOString(),
  };
}

export function loadGraph(): GraphDoc {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return emptyGraph();
    const parsed = JSON.parse(raw) as GraphDoc;
    if (!parsed || !Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) {
      return emptyGraph();
    }
    return {
      name: typeof parsed.name === "string" ? parsed.name : "Новая схема",
      nodes: parsed.nodes,
      edges: parsed.edges,
      updatedAt: parsed.updatedAt || new Date().toISOString(),
    };
  } catch {
    return emptyGraph();
  }
}

export function saveGraph(doc: GraphDoc): void {
  try {
    const next: GraphDoc = {
      ...doc,
      updatedAt: new Date().toISOString(),
    };
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* quota */
  }
}

/** Local persistence for agent graph canvas. */

import type { Edge, Node } from "@xyflow/react";

import { cloneDemoGraph } from "./templates";
import type { AgentNodeData } from "./types";

const KEY = "aichallenge.agent_graph.v2";
const LEGACY_KEY = "aichallenge.agent_graph.v1";

export type GraphDoc = {
  name: string;
  nodes: Node<AgentNodeData>[];
  edges: Edge[];
  updatedAt: string;
};

function parseDoc(raw: string): GraphDoc | null {
  try {
    const parsed = JSON.parse(raw) as GraphDoc;
    if (!parsed || !Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) {
      return null;
    }
    return {
      name: typeof parsed.name === "string" ? parsed.name : "Новая схема",
      nodes: parsed.nodes,
      edges: parsed.edges,
      updatedAt: parsed.updatedAt || new Date().toISOString(),
    };
  } catch {
    return null;
  }
}

/** Default / empty boot → showcase demo (not a blank canvas). */
export function emptyGraph(name?: string): GraphDoc {
  return cloneDemoGraph(name);
}

export function loadGraph(): GraphDoc {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const doc = parseDoc(raw);
      if (doc && doc.nodes.length > 0) return doc;
      return emptyGraph();
    }

    const legacy = localStorage.getItem(LEGACY_KEY);
    if (legacy) {
      const doc = parseDoc(legacy);
      if (doc && doc.nodes.length > 0) {
        saveGraph(doc);
        return doc;
      }
    }

    return emptyGraph();
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

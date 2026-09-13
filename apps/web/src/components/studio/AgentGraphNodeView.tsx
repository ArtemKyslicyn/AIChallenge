import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { NODE_KIND_LABEL, type AgentNodeData, type GraphNodeKind } from "../../studio/types";

export type AgentGraphNode = Node<AgentNodeData, "agentGraph">;

const KIND_CLASS: Record<GraphNodeKind, string> = {
  start: "ag-node--start",
  agent: "ag-node--agent",
  merge: "ag-node--merge",
  end: "ag-node--end",
};

export function AgentGraphNodeView({ data, selected }: NodeProps<AgentGraphNode>) {
  const kind = data.kind;
  const showIn = kind !== "start";
  const showOut = kind !== "end";
  const run = data.runState || "idle";

  return (
    <div
      className={`ag-node ${KIND_CLASS[kind]}${selected ? " is-selected" : ""} ag-node--${run}`}
      title={NODE_KIND_LABEL[kind]}
    >
      {showIn ? (
        <Handle type="target" position={Position.Left} id="in" className="ag-handle" />
      ) : null}
      <div className="ag-node-kind">{NODE_KIND_LABEL[kind]}</div>
      <div className="ag-node-label">{data.label}</div>
      {kind === "agent" && data.preferredModel ? (
        <div className="ag-node-meta">{data.preferredModel}</div>
      ) : null}
      {run !== "idle" ? <div className="ag-node-run">{run}</div> : null}
      {showOut ? (
        <Handle type="source" position={Position.Right} id="out" className="ag-handle" />
      ) : null}
    </div>
  );
}

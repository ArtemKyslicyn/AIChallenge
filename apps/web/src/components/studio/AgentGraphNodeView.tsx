import {
  Handle,
  Position,
  type Node,
  type NodeProps,
} from "@xyflow/react";

import { NODE_KIND_LABEL, type AgentNodeData, type GraphNodeKind } from "../../studio/types";

export type AgentGraphNode = Node<AgentNodeData, "agentGraph">;

const KIND_CLASS: Record<GraphNodeKind, string> = {
  start: "ag-node--start",
  agent: "ag-node--agent",
  merge: "ag-node--merge",
  end: "ag-node--end",
};

const RUN_LABEL: Record<string, string> = {
  running: "идёт",
  done: "готово",
  error: "ошибка",
};

export function AgentGraphNodeView({ data, selected }: NodeProps<AgentGraphNode>) {
  const kind = data.kind;
  const showIn = kind !== "start";
  const showOut = kind !== "end";
  const run = data.runState || "idle";

  return (
    <div
      className={`ag-node ${KIND_CLASS[kind]}${selected ? " is-selected" : ""} ag-node--${run}`}
    >
      {showIn ? (
        <>
          <Handle
            type="target"
            position={Position.Left}
            id="in"
            className="ag-handle ag-handle--in"
            isConnectable
          />
          <Handle
            type="target"
            position={Position.Top}
            id="in-top"
            className="ag-handle ag-handle--in ag-handle--aux"
            isConnectable
          />
        </>
      ) : null}
      <div className="ag-node-head">
        <span className="ag-node-kind">{NODE_KIND_LABEL[kind]}</span>
        {run !== "idle" ? (
          <span className={`ag-node-run ag-node-run--${run}`}>{RUN_LABEL[run] || run}</span>
        ) : null}
      </div>
      <div className="ag-node-label">{data.label}</div>
      {kind === "agent" && data.preferredModel ? (
        <div className="ag-node-meta">{data.preferredModel}</div>
      ) : null}
      {showOut ? (
        <>
          <Handle
            type="source"
            position={Position.Right}
            id="out"
            className="ag-handle ag-handle--out"
            isConnectable
          />
          <Handle
            type="source"
            position={Position.Bottom}
            id="out-bottom"
            className="ag-handle ag-handle--out ag-handle--aux"
            isConnectable
          />
        </>
      ) : null}
    </div>
  );
}

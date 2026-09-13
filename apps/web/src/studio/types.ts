/** Agent graph types for «Схема Агентов» canvas. */

export type GraphNodeKind = "start" | "agent" | "merge" | "end";

export interface AgentNodeData extends Record<string, unknown> {
  kind: GraphNodeKind;
  label: string;
  /** Optional link to workshop draft id */
  draftId?: string | null;
  systemPrompt?: string;
  preferredModel?: string;
  runState?: "idle" | "running" | "done" | "error";
}

export const NODE_KIND_LABEL: Record<GraphNodeKind, string> = {
  start: "Старт",
  agent: "Агент",
  merge: "Слияние",
  end: "Конец",
};

export const PALETTE: { kind: GraphNodeKind; hint: string }[] = [
  { kind: "start", hint: "Вход пользователя" },
  { kind: "agent", hint: "LLM-агент" },
  { kind: "merge", hint: "Собрать ответы" },
  { kind: "end", hint: "Результат" },
];

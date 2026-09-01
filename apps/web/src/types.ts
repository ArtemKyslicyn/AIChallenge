export interface Turn {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Which model produced this reply. Null until the model event arrives. */
  modelId: string | null;
  /** The answer was cut short — by the provider or by the reader stopping it. */
  failed?: boolean;
}

export interface CompareSlotState {
  loading: boolean;
  error: string | null;
  content: string;
  modelId: string | null;
  aborted?: boolean;
}

/** Side-by-side probe pair in the thread (not persisted on the server). */
export interface CompareTurn {
  kind: "compare";
  id: string;
  templateLabel: string;
  baseline: CompareSlotState;
  constrained: CompareSlotState;
}

export type ThreadItem = Turn | CompareTurn;

export function isCompareTurn(item: ThreadItem): item is CompareTurn {
  return "kind" in item && item.kind === "compare";
}

export function isTurn(item: ThreadItem): item is Turn {
  return !isCompareTurn(item);
}

export const EMPTY_COMPARE_SLOT: CompareSlotState = {
  loading: true,
  error: null,
  content: "",
  modelId: null,
};

import type { ExpertSlotResult } from "./strategies/runStrategy";
import type { JudgeScorecard } from "./strategies/judge";
import type { PromptStrategyId } from "./strategies/types";

export type MediaJobKind = "image" | "video";

export interface MediaJobState {
  kind: MediaJobKind;
  phase: "running" | "done" | "error";
  startedAt: number;
  providerLabel?: string | null;
  error?: string | null;
}

export interface Turn {
  id: string;
  role: "user" | "assistant";
  content: string;
  modelId: string | null;
  failed?: boolean;
  /** Live media generation job (image / video) for in-bubble loader. */
  mediaJob?: MediaJobState | null;
  /**
   * Server message id (prep D10). History turns carry it from the start; a live
   * reply only gets one at `message_end`, so its absence is exactly «no rating
   * mid-stream» — `FeedbackStrip` mounts only once this is set.
   */
  messageId?: string | null;
  /** Vote the server already holds for this message — seeds `FeedbackStrip`. */
  feedback?: "up" | "down" | null;
}

export interface ProbeSlotState {
  loading: boolean;
  error: string | null;
  content: string;
  modelId: string | null;
  aborted?: boolean;
  statusHint?: string | null;
  metaPrompt?: string | null;
  expertSlots?: ExpertSlotResult[];
  latencyMs?: number;
}

export type CompareSlotState = ProbeSlotState;

export interface CompareTurn {
  kind: "compare";
  id: string;
  templateLabel: string;
  baseline: ProbeSlotState;
  constrained: ProbeSlotState;
}

export interface LabTurn {
  kind: "lab";
  id: string;
  taskDisplay: string;
  slots: Record<PromptStrategyId, ProbeSlotState>;
  judge?: JudgeScorecard | null;
  goldenAnswer?: string;
  compact?: boolean;
}

export type ThreadItem = Turn | CompareTurn | LabTurn;

export function isCompareTurn(item: ThreadItem): item is CompareTurn {
  return "kind" in item && item.kind === "compare";
}

export function isLabTurn(item: ThreadItem): item is LabTurn {
  return "kind" in item && item.kind === "lab";
}

export function isTurn(item: ThreadItem): item is Turn {
  return !isCompareTurn(item) && !isLabTurn(item);
}

export const EMPTY_PROBE_SLOT: ProbeSlotState = {
  loading: true,
  error: null,
  content: "",
  modelId: null,
};

export const EMPTY_COMPARE_SLOT = EMPTY_PROBE_SLOT;

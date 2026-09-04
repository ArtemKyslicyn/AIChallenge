import type { CascadeStage } from "./api/client";
import type { ComicStripState } from "./comic";
import type { ExpertSlotResult } from "./strategies/runStrategy";
import type { JudgeScorecard } from "./strategies/judge";
import type { TempJudgeScorecard } from "./strategies/tempJudge";
import type { TempSlotId } from "./strategies/tempStudio";
import type { PromptStrategyId } from "./strategies/types";

export type MediaJobKind = "image" | "video" | "comic";

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
  /** Live media generation job (image / video / comic) for in-bubble loader. */
  mediaJob?: MediaJobState | null;
  /** Live or hydrated comic strip (HTML overlays on Pollinations art). */
  comic?: ComicStripState | null;
  /**
   * Server message id (prep D10). History turns carry it from the start; a live
   * reply only gets one at `message_end`, so its absence is exactly «no rating
   * mid-stream» — `FeedbackStrip` mounts only once this is set.
   */
  messageId?: string | null;
  /** Vote the server already holds for this message — seeds `FeedbackStrip`. */
  feedback?: "up" | "down" | null;
  /**
   * Which stage of the cascade answered. Set from history by `toTurn` and
   * live at `message_end`, exactly like `messageId` — a streaming reply has
   * no stage yet, and that is right: the badge lands with the answer, not
   * halfway through it.
   */
  cascadeStage?: CascadeStage;
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

/** Temperature studio: same prompt at three temperatures + auto scorecard. */
export interface TempStudioTurn {
  kind: "temp_studio";
  id: string;
  taskDisplay: string;
  /** Temperatures used for this run (slot id → t). */
  temps: Record<TempSlotId, number>;
  slots: Record<TempSlotId, ProbeSlotState>;
  judge?: TempJudgeScorecard | null;
  judgeLoading?: boolean;
}

export type ThreadItem = Turn | CompareTurn | LabTurn | TempStudioTurn;

export function isCompareTurn(item: ThreadItem): item is CompareTurn {
  return "kind" in item && item.kind === "compare";
}

export function isLabTurn(item: ThreadItem): item is LabTurn {
  return "kind" in item && item.kind === "lab";
}

export function isTempStudioTurn(item: ThreadItem): item is TempStudioTurn {
  return "kind" in item && item.kind === "temp_studio";
}

export function isTurn(item: ThreadItem): item is Turn {
  return !isCompareTurn(item) && !isLabTurn(item) && !isTempStudioTurn(item);
}

export const EMPTY_PROBE_SLOT: ProbeSlotState = {
  loading: true,
  error: null,
  content: "",
  modelId: null,
};

export const EMPTY_COMPARE_SLOT = EMPTY_PROBE_SLOT;

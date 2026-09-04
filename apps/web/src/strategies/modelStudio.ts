/** Day-5 Performance Studio: same prompt on weak / mid / strong models. */

export type ModelTierId = "weak" | "mid" | "strong";

export interface ModelTierDef {
  id: ModelTierId;
  /** Short RU label for the column. */
  label: string;
  /** One-line expectation. */
  hint: string;
  accent: "weak" | "mid" | "strong";
}

export const MODEL_TIER_IDS: ModelTierId[] = ["weak", "mid", "strong"];

export const MODEL_TIERS: readonly ModelTierDef[] = [
  {
    id: "weak",
    label: "Слабая",
    hint: "Быстрее и дешевле — база для черновиков",
    accent: "weak",
  },
  {
    id: "mid",
    label: "Средняя",
    hint: "Баланс качества и цены",
    accent: "mid",
  },
  {
    id: "strong",
    label: "Сильная",
    hint: "Максимум качества — дороже и медленнее",
    accent: "strong",
  },
] as const;

export const DEFAULT_STUDIO_PROMPT =
  "Объясни новичку, что такое temperature у LLM, в 5–7 предложениях. Приведи один бытовой пример.";

/** Pick weak / mid / strong ids from the live catalog (start / middle / end). */
export function pickDefaultTier(modelIds: string[]): Record<ModelTierId, string> {
  const usable = modelIds.filter((id) => id && id !== "auto");
  if (usable.length === 0) {
    return { weak: "auto", mid: "auto", strong: "auto" };
  }
  if (usable.length === 1) {
    return { weak: usable[0], mid: usable[0], strong: usable[0] };
  }
  if (usable.length === 2) {
    return { weak: usable[0], mid: usable[1], strong: usable[1] };
  }
  const mid = Math.floor((usable.length - 1) / 2);
  return {
    weak: usable[0],
    mid: usable[mid],
    strong: usable[usable.length - 1],
  };
}

/** Rough completion tokens — same heuristic as API run traces (`chars/4`). */
export function estimateTokens(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) return 0;
  return Math.max(1, Math.round(trimmed.length / 4));
}

/**
 * Relative cost proxy (not billing). Free / flash / flagship heuristics so the
 * Day-5 dashboard can compare resource cost without a provider invoice.
 */
export function estimateCostProxy(modelId: string | null | undefined): number {
  if (!modelId) return 1;
  const id = modelId.toLowerCase();
  if (id.includes(":free") || id.endsWith("/free") || id.includes("openrouter/free")) {
    return 0.05;
  }
  if (id.includes("nano") || id.includes("mini") || id.includes("flash") || id.includes("haiku")) {
    return 0.4;
  }
  if (
    id.includes("235b") ||
    id.includes("ultra") ||
    id.includes("opus") ||
    id.includes("gpt-4") ||
    id.includes("o1") ||
    id.includes("o3")
  ) {
    return 3.0;
  }
  if (id.includes("v3.2") || id.includes("v3") || id.includes("sonnet") || id.includes("pro")) {
    return 1.6;
  }
  return 1.0;
}

/** Public model card link (OpenRouter-style id → openrouter; else search). */
export function modelCardUrl(modelId: string): string {
  const id = modelId.trim();
  if (!id || id === "auto") return "https://openrouter.ai/models";
  if (id.includes("/")) {
    return `https://openrouter.ai/${id}`;
  }
  return `https://huggingface.co/models?search=${encodeURIComponent(id)}`;
}

export function formatLatency(ms: number | null | undefined): string {
  if (typeof ms !== "number" || !Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} мс`;
  return `${(ms / 1000).toFixed(1)} с`;
}

export function formatTokens(n: number | null | undefined): string {
  if (typeof n !== "number" || !Number.isFinite(n) || n <= 0) return "—";
  return String(n);
}

export function formatCost(n: number | null | undefined): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  return n < 0.1 ? n.toFixed(2) : n.toFixed(1);
}

/** 0–1 bar fill relative to the worst (highest) value in the set. */
export function relativeBar(value: number, worst: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(worst) || worst <= 0) return 0;
  return Math.max(0.06, Math.min(1, value / worst));
}

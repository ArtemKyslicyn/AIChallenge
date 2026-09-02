/** Prompt strategy ids for the four-way lab (challenge demo). */

export type PromptStrategyId = "direct" | "step_by_step" | "meta_prompt" | "expert_panel";

export interface PromptStrategyDef {
  id: PromptStrategyId;
  label: string;
  shortLabel: string;
  hint: string;
  /** Accent for lab grid headers. */
  accent: "neutral" | "steps" | "meta" | "experts";
}

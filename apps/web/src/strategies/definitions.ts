import type { PromptStrategyDef, PromptStrategyId } from "./types";

export const PROMPT_STRATEGIES: readonly PromptStrategyDef[] = [
  {
    id: "direct",
    label: "Прямой ответ",
    shortLabel: "Прямой",
    hint: "Задача без дополнительных инструкций — baseline.",
    accent: "neutral",
  },
  {
    id: "step_by_step",
    label: "Пошагово",
    shortLabel: "Пошагово",
    hint: "Явная инструкция решать по шагам с проверкой.",
    accent: "steps",
  },
  {
    id: "meta_prompt",
    label: "Meta-prompt",
    shortLabel: "Meta",
    hint: "Сначала модель составляет промпт, затем отвечает по нему (2 фазы).",
    accent: "meta",
  },
  {
    id: "expert_panel",
    label: "Панель экспертов",
    shortLabel: "Эксперты",
    hint: "Ответы от аналитика, инженера и критика в одном сообщении.",
    accent: "experts",
  },
] as const;

export const PROMPT_STRATEGY_IDS: PromptStrategyId[] = PROMPT_STRATEGIES.map((s) => s.id);

export function strategyById(id: PromptStrategyId): PromptStrategyDef {
  return PROMPT_STRATEGIES.find((s) => s.id === id) ?? PROMPT_STRATEGIES[0];
}

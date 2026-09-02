import type { PromptStrategyId } from "./types";

export type ExpertRoleId = "analyst" | "engineer" | "critic" | "synthesis";

export const EXPERT_ROLES: readonly {
  id: ExpertRoleId;
  label: string;
  promptHint: string;
}[] = [
  {
    id: "analyst",
    label: "Аналитик",
    promptHint: "Уточни данные, допущения и модель задачи. Без финального числа, если не уверен.",
  },
  {
    id: "engineer",
    label: "Инженер",
    promptHint: "Покажи алгоритм и полный расчёт. В конце — явный итог.",
  },
  {
    id: "critic",
    label: "Критик",
    promptHint: "Найди возможные ошибки и перепроверь. Дай свой вердикт по ответу.",
  },
] as const;

const STEP_BY_STEP_BLOCK = [
  "Инструкция: решай задачу пошагово.",
  "Каждый шаг — отдельная нумерованная строка (1., 2., …).",
  "В конце дай итоговый ответ и короткую проверку расчёта.",
].join("\n");

export const META_PHASE1_INSTRUCTION = [
  "Ты помогаешь составить промпт для другой модели.",
  "По задаче пользователя напиши только промпт для решения — без самого решения.",
  "Промпт должен быть самодостаточным и на русском языке.",
].join("\n");

function appendSessionContext(task: string, sessionContext: string): string {
  const base = task.trim();
  const ctx = sessionContext.trim();
  if (!ctx) return base;
  return `${base}\n\nКонтекст чата:\n${ctx}`;
}

export function buildExpertRolePrompt(
  roleId: Exclude<ExpertRoleId, "synthesis">,
  taskText: string,
  sessionContext = "",
): string {
  const task = appendSessionContext(taskText, sessionContext);
  const role = EXPERT_ROLES.find((r) => r.id === roleId)!;
  return [
    `Ты — ${role.label}.`,
    role.promptHint,
    "Отвечай на русском. Не изображай другие роли.",
    "",
    "Задача:",
    task,
  ].join("\n");
}

export function buildExpertSynthesisPrompt(
  taskText: string,
  parts: { analyst: string; engineer: string; critic: string },
  sessionContext = "",
): string {
  const task = appendSessionContext(taskText, sessionContext);
  return [
    "Ты — редактор-синтезатор. На основе трёх экспертиз дай единый итоговый ответ.",
    "Структура: краткий вывод → расчёт при необходимости → проверка.",
    "Если эксперты расходятся — выбери наиболее обоснованный вариант и объясни почему.",
    "",
    "Задача:",
    task,
    "",
    "Аналитик:",
    parts.analyst || "(пусто)",
    "",
    "Инженер:",
    parts.engineer || "(пусто)",
    "",
    "Критик:",
    parts.critic || "(пусто)",
  ].join("\n");
}

/** User-facing prompt for a single probe call (except meta phase 2 / expert multi). */
export function buildStrategyPrompt(
  strategyId: PromptStrategyId,
  taskText: string,
  sessionContext = "",
): string {
  const task = appendSessionContext(taskText, sessionContext);

  switch (strategyId) {
    case "direct":
      return task;
    case "step_by_step":
      return `${task}\n\n${STEP_BY_STEP_BLOCK}`;
    case "meta_prompt":
      return `${META_PHASE1_INSTRUCTION}\n\nЗадача:\n${task}`;
    case "expert_panel":
      // Multi-call path uses buildExpertRolePrompt; this is fallback single-call.
      return `${task}\n\nОтветь кратко от лица трёх экспертов (Аналитик / Инженер / Критик), затем Итог.`;
    default:
      return task;
  }
}

export function buildMetaPhase2Prompt(generatedPrompt: string): string {
  return generatedPrompt.trim();
}

export function buildJudgePrompt(
  task: string,
  goldenAnswer: string,
  rubric: string,
  answers: { id: string; label: string; content: string }[],
): string {
  const blocks = answers
    .map(
      (a, i) =>
        `### Вариант ${i + 1}: ${a.label} (id=${a.id})\n${a.content.trim() || "(пусто)"}`,
    )
    .join("\n\n");
  return [
    "Ты — независимый судья качества решений.",
    "Сравни ответы на одну задачу. Не решай задачу заново с нуля — оценивай ответы.",
    goldenAnswer ? `Эталонный ответ (кратко): ${goldenAnswer}` : "Эталон не задан — оцени логику и полноту.",
    rubric ? `Критерии: ${rubric}` : "",
    "",
    "Задача:",
    task.trim(),
    "",
    blocks,
    "",
    "Верни СТРОГО JSON без markdown-ограждений:",
    '{"winner_id":"<id лучшего>","scores":{"direct":0,"step_by_step":0,"meta_prompt":0,"expert_panel":0},"rationale":"1-2 предложения на русском","accuracy_notes":"кратко"}',
    "Баллы scores — целые 0..10. winner_id должен быть одним из id вариантов.",
  ]
    .filter(Boolean)
    .join("\n");
}

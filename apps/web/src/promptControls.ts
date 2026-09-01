/** Outcome-oriented prompt wrappers for the composer (format / length / stop). */

export type PromptControlId = "format" | "length" | "stop";

export interface PromptControlFlags {
  format: boolean;
  length: boolean;
  stop: boolean;
}

export const EMPTY_PROMPT_CONTROLS: PromptControlFlags = {
  format: false,
  length: false,
  stop: false,
};

export interface PromptControlDef {
  id: PromptControlId;
  /** Short label on the chip — what the user gets, not the mechanism. */
  label: string;
  /** Tooltip / title. */
  hint: string;
  block: string;
}

export const PROMPT_CONTROLS: readonly PromptControlDef[] = [
  {
    id: "format",
    label: "Списком",
    hint: "Ответ ровно тремя пронумерованными пунктами",
    block:
      "Формат ответа: ровно 3 пункта, каждый с новой строки, с префиксами «1. », «2. », «3. ». Без вступления и без текста вне пунктов.",
  },
  {
    id: "length",
    label: "Кратко",
    hint: "Не больше 50 слов в ответе",
    block: "Ограничение длины: не больше 50 слов во всём ответе.",
  },
  {
    id: "stop",
    label: "Чёткий конец",
    hint: "После ответа — одна строка END, больше ничего",
    block:
      "Условие завершения: после основного ответа напиши отдельной строкой ровно END и больше ничего не добавляй.",
  },
] as const;

const SEPARATOR = "\n\n— Как отвечать —\n";

export const CUSTOM_RULES_MAX_CHARS = 500;

export const CUSTOM_RULE_EXAMPLES = [
  { label: "По-русски", text: "Отвечай только на русском языке." },
  { label: "Сначала вывод", text: "Первая строка — краткий вывод, затем пояснение." },
  { label: "Без вступления", text: "Без приветствий и повторения вопроса." },
] as const;

export function anyPromptControl(flags: PromptControlFlags): boolean {
  return flags.format || flags.length || flags.stop;
}

function ruleBlocks(flags: PromptControlFlags): string[] {
  return PROMPT_CONTROLS.filter((c) => flags[c.id]).map((c) => c.block);
}

/** Build the text that goes to the model; keeps the user question first. */
export function applyPromptControls(userText: string, flags: PromptControlFlags): string {
  const trimmed = userText.trim();
  if (!trimmed || !anyPromptControl(flags)) return trimmed;
  return `${trimmed}${SEPARATOR}${ruleBlocks(flags).join("\n")}`;
}

/** Apply preset template, chip toggles, or free-form custom rules. */
export function applyResponseTemplate(
  userText: string,
  templateId: ResponseTemplateId,
  promptControls: PromptControlFlags,
  customRulesText: string,
): string {
  const trimmed = userText.trim();
  if (!trimmed) return trimmed;

  const parts: string[] = [];

  if (templateId === "custom") {
    parts.push(...ruleBlocks(promptControls));
    const custom = customRulesText.trim();
    if (custom) parts.push(custom);
  } else {
    const controls = resolvePromptControls(templateId, promptControls);
    parts.push(...ruleBlocks(controls));
  }

  if (parts.length === 0) return trimmed;
  return `${trimmed}${SEPARATOR}${parts.join("\n")}`;
}

export function previewResponseRules(
  templateId: ResponseTemplateId,
  promptControls: PromptControlFlags,
  customRulesText: string,
): string | null {
  const sample = applyResponseTemplate("Пример вопроса", templateId, promptControls, customRulesText);
  const prefix = "Пример вопроса";
  if (!sample.startsWith(prefix)) return null;
  const suffix = sample.slice(prefix.length);
  return suffix.trim() ? suffix.trim() : null;
}

export function hasResponseRules(
  templateId: ResponseTemplateId,
  promptControls: PromptControlFlags,
  customRulesText: string,
): boolean {
  if (templateId === "free") return false;
  if (templateId === "custom") {
    return anyPromptControl(promptControls) || Boolean(customRulesText.trim());
  }
  return true;
}

export function activeControlLabels(flags: PromptControlFlags): string[] {
  return PROMPT_CONTROLS.filter((c) => flags[c.id]).map((c) => c.label);
}

/** Preset response-shape templates (settings). ``custom`` uses ``promptControls`` toggles. */
export type ResponseTemplateId = "free" | "bullets" | "brief" | "structured" | "custom";

export interface ResponseTemplate {
  id: ResponseTemplateId;
  label: string;
  hint: string;
  controls: PromptControlFlags;
}

export const RESPONSE_TEMPLATES: readonly ResponseTemplate[] = [
  {
    id: "free",
    label: "Свободный",
    hint: "Без ограничений формата",
    controls: { format: false, length: false, stop: false },
  },
  {
    id: "bullets",
    label: "3 пункта",
    hint: "Ровно три пронумерованных пункта",
    controls: { format: true, length: false, stop: false },
  },
  {
    id: "brief",
    label: "Кратко",
    hint: "Не больше 50 слов",
    controls: { format: false, length: true, stop: false },
  },
  {
    id: "structured",
    label: "Полный шаблон",
    hint: "3 пункта, кратко и строка END",
    controls: { format: true, length: true, stop: true },
  },
  {
    id: "custom",
    label: "Свои правила",
    hint: "Опишите формат текстом и при необходимости включите быстрые дополнения",
    controls: { ...EMPTY_PROMPT_CONTROLS },
  },
] as const;

export function templateById(id: ResponseTemplateId): ResponseTemplate {
  return RESPONSE_TEMPLATES.find((t) => t.id === id) ?? RESPONSE_TEMPLATES[0];
}

/** Effective prompt flags: preset template or manual toggles for ``custom``. */
export function resolvePromptControls(
  templateId: ResponseTemplateId,
  manual: PromptControlFlags,
): PromptControlFlags {
  if (templateId === "custom") return manual;
  return templateById(templateId).controls;
}

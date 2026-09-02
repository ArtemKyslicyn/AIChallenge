import type { EffectiveChatPrefs, GlobalChatPrefs } from "./types";
import {
  applyResponseTemplate,
  type PromptControlFlags,
  type ResponseTemplateId,
} from "../promptControls";

const LANGUAGE_BLOCKS: Record<"ru" | "en", string> = {
  ru: "Отвечай на русском языке.",
  en: "Reply in English.",
};

function applyLanguageHint(text: string, hint: GlobalChatPrefs["languageHint"]): string {
  if (hint !== "ru" && hint !== "en") return text;
  const block = LANGUAGE_BLOCKS[hint];
  if (text.includes(block)) return text;
  return `${text}\n\n${block}`;
}

export interface OutgoingPayload {
  /** Shown in the thread — the user's own wording. */
  display: string;
  /** Sent to the API — may include rules and session context. */
  api: string;
  modelId: string;
  effective: EffectiveChatPrefs;
}

export function buildOutgoingMessage(
  userText: string,
  effective: EffectiveChatPrefs,
  global: GlobalChatPrefs,
  manualControls: PromptControlFlags,
): OutgoingPayload {
  const display = userText.trim();
  let api = applyResponseTemplate(
    display,
    effective.responseTemplateId,
    manualControls,
    effective.customRulesText,
  );

  if (effective.sessionContext) {
    api = `${api}\n\nКонтекст чата:\n${effective.sessionContext}`;
  }

  api = applyLanguageHint(api, global.languageHint);

  return {
    display,
    api,
    modelId: effective.modelId,
    effective,
  };
}

/** Label for compare constrained column. */
export function templateLabelForCompare(
  responseTemplateId: ResponseTemplateId,
  _promptControls: PromptControlFlags,
  customRulesText: string,
): string {
  if (responseTemplateId === "custom") {
    const custom = customRulesText.trim();
    if (custom) {
      const short = custom.length > 28 ? `${custom.slice(0, 28)}…` : custom;
      return `С правилами: ${short}`;
    }
    return "С шаблоном";
  }
  if (responseTemplateId === "free") return "С шаблоном";
  const labels: Record<ResponseTemplateId, string> = {
    free: "С шаблоном",
    bullets: "Шаблон: 3 пункта",
    brief: "Шаблон: Кратко",
    structured: "Шаблон: Полный",
    custom: "С шаблоном",
  };
  return labels[responseTemplateId] ?? "С шаблоном";
}

export function prefsToProbeBody(effective: EffectiveChatPrefs) {
  return {
    model: effective.modelId,
    temperature: effective.temperature,
    reasoning: effective.reasoning,
    prompt_format: effective.promptControls.format,
    prompt_length: effective.promptControls.length,
    prompt_stop: effective.promptControls.stop,
  };
}

/**
 * Back-compat re-exports. Prefer `chatPrefs` and `strategies` for new code.
 */

import {
  loadGlobalChatPrefs,
  mergeChatPrefs,
  type ChatMode,
  type EffectiveChatPrefs,
} from "./chatPrefs";
import {
  buildOutgoingMessage as buildOutgoing,
  prefsToProbeBody as probeBody,
  templateLabelForCompare as compareLabel,
} from "./chatPrefs/outgoing";
import {
  activeControlLabels,
  applyResponseTemplate,
  CUSTOM_RULES_MAX_CHARS,
  EMPTY_PROMPT_CONTROLS,
  hasResponseRules,
  previewResponseRules,
  resolvePromptControls,
  RESPONSE_TEMPLATES,
  templateById,
  type PromptControlFlags,
  type ResponseTemplateId,
} from "./promptControls";

export type GenerationPrefs = EffectiveChatPrefs & {
  /** @deprecated use chatMode */
  compareMode: boolean;
  responseTemplateId: ResponseTemplateId;
  promptControls: PromptControlFlags;
  customRulesText: string;
};

export const GENERATION_PREFS_KEY = "aichallenge.generation_prefs";
export const DEFAULT_GENERATION_PREFS = loadGlobalChatPrefs();

export function loadGenerationPrefs(): GenerationPrefs {
  const global = loadGlobalChatPrefs();
  const effective = mergeChatPrefs(global, {
    chatMode: global.defaultChatMode,
    modelIdOverride: "",
    temperatureOverride: null,
    reasoningOverride: null,
    responseTemplateIdOverride: null,
    promptControlsOverride: null,
    customRulesOverride: null,
    sessionContext: "",
    tempStudioTemps: [0, 0.7, 1.2],
  });
  return toLegacyPrefs(effective, global.responseTemplateId, global.promptControls, global.customRulesText);
}

export function saveGenerationPrefs(_prefs: GenerationPrefs): void {
  // Legacy no-op — Composer now saves global + session separately.
}

function toLegacyPrefs(
  effective: EffectiveChatPrefs,
  responseTemplateId: ResponseTemplateId,
  promptControls: PromptControlFlags,
  customRulesText: string,
): GenerationPrefs {
  return {
    ...effective,
    compareMode: effective.chatMode === "compare",
    responseTemplateId,
    promptControls,
    customRulesText,
  };
}

export function effectivePromptControls(prefs: Pick<GenerationPrefs, "responseTemplateId" | "promptControls">) {
  return resolvePromptControls(prefs.responseTemplateId, prefs.promptControls);
}

export function responseRulesActive(prefs: Pick<GenerationPrefs, "responseTemplateId" | "promptControls" | "customRulesText">) {
  return hasResponseRules(prefs.responseTemplateId, prefs.promptControls, prefs.customRulesText);
}

export function activeTemplateSummary(prefs: Pick<GenerationPrefs, "responseTemplateId" | "promptControls" | "customRulesText">): string | null {
  if (prefs.responseTemplateId === "free") return null;
  if (prefs.responseTemplateId === "custom") {
    const bits: string[] = [];
    if (prefs.promptControls.format) bits.push("списком");
    if (prefs.promptControls.length) bits.push("кратко");
    if (prefs.promptControls.stop) bits.push("чёткий конец");
    const custom = prefs.customRulesText.trim();
    if (custom) {
      const short = custom.length > 36 ? `${custom.slice(0, 36)}…` : custom;
      bits.push(`«${short}»`);
    }
    return bits.length ? bits.join(" · ") : null;
  }
  return templateById(prefs.responseTemplateId).label;
}

export function buildOutgoingMessage(userText: string, prefs: GenerationPrefs) {
  const global = loadGlobalChatPrefs();
  const payload = buildOutgoing(userText, prefs, global, prefs.promptControls);
  return {
    display: payload.display,
    api: payload.api,
    modelId: payload.modelId,
    compareMode: prefs.chatMode === "compare",
    chatMode: prefs.chatMode as ChatMode,
    prefs,
  };
}

export function prefsToProbeBody(prefs: EffectiveChatPrefs) {
  return probeBody(prefs);
}

export function templateLabelForCompare(prefs: Pick<GenerationPrefs, "responseTemplateId" | "promptControls" | "customRulesText">) {
  return compareLabel(prefs.responseTemplateId, prefs.promptControls, prefs.customRulesText);
}

export function countWords(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) return 0;
  return trimmed.split(/\s+/).length;
}

export function hasNumberedTriplet(text: string): boolean {
  return [1, 2, 3].every((n) => new RegExp(`^${n}\\.\\s`, "m").test(text));
}

export function hasEndMarker(text: string): boolean {
  return /^END\s*$/m.test(text);
}

export function hasExpertSections(text: string): boolean {
  return /Аналитик\s*:/i.test(text) && /Инженер\s*:/i.test(text) && /Критик\s*:/i.test(text);
}

export function hasNumberedSteps(text: string): boolean {
  return /^1\.\s/m.test(text) && /^2\.\s/m.test(text);
}

export {
  CUSTOM_RULES_MAX_CHARS,
  previewResponseRules,
  RESPONSE_TEMPLATES,
  EMPTY_PROMPT_CONTROLS,
  applyResponseTemplate,
  activeControlLabels,
  hasResponseRules,
};

/** Saved probe/chat generation preferences (localStorage). */

import {
  CUSTOM_RULES_MAX_CHARS,
  EMPTY_PROMPT_CONTROLS,
  RESPONSE_TEMPLATES,
  applyResponseTemplate,
  hasResponseRules,
  resolvePromptControls,
  templateById,
  type PromptControlFlags,
  type ResponseTemplateId,
} from "./promptControls";

export const GENERATION_PREFS_KEY = "aichallenge.generation_prefs";

export interface GenerationPrefs {
  modelId: string;
  temperature: number;
  reasoning: boolean;
  responseTemplateId: ResponseTemplateId;
  promptControls: PromptControlFlags;
  /** Free-form instructions when ``responseTemplateId === "custom"``. */
  customRulesText: string;
  compareMode: boolean;
}

export const DEFAULT_GENERATION_PREFS: GenerationPrefs = {
  modelId: "auto",
  temperature: 0.7,
  reasoning: false,
  responseTemplateId: "free",
  promptControls: { ...EMPTY_PROMPT_CONTROLS },
  customRulesText: "",
  compareMode: false,
};

function inferTemplateId(
  controls: PromptControlFlags,
  customRulesText: string,
): ResponseTemplateId {
  if (customRulesText.trim()) return "custom";
  for (const template of RESPONSE_TEMPLATES) {
    if (template.id === "custom" || template.id === "free") continue;
    if (
      template.controls.format === controls.format &&
      template.controls.length === controls.length &&
      template.controls.stop === controls.stop
    ) {
      return template.id;
    }
  }
  if (controls.format || controls.length || controls.stop) return "custom";
  return "free";
}

export function loadGenerationPrefs(): GenerationPrefs {
  try {
    const raw = localStorage.getItem(GENERATION_PREFS_KEY);
    if (!raw) return { ...DEFAULT_GENERATION_PREFS, promptControls: { ...EMPTY_PROMPT_CONTROLS } };
    const parsed = JSON.parse(raw) as Partial<GenerationPrefs> & {
      promptControls?: Partial<PromptControlFlags>;
    };
    const promptControls: PromptControlFlags = {
      format: Boolean(parsed.promptControls?.format),
      length: Boolean(parsed.promptControls?.length),
      stop: Boolean(parsed.promptControls?.stop),
    };
    const customRulesText =
      typeof parsed.customRulesText === "string"
        ? parsed.customRulesText.slice(0, CUSTOM_RULES_MAX_CHARS)
        : "";
    const responseTemplateId =
      parsed.responseTemplateId ?? inferTemplateId(promptControls, customRulesText);
    return {
      modelId: parsed.modelId ?? DEFAULT_GENERATION_PREFS.modelId,
      temperature:
        typeof parsed.temperature === "number"
          ? parsed.temperature
          : DEFAULT_GENERATION_PREFS.temperature,
      reasoning: Boolean(parsed.reasoning),
      responseTemplateId,
      promptControls,
      customRulesText,
      compareMode: Boolean(parsed.compareMode),
    };
  } catch {
    return { ...DEFAULT_GENERATION_PREFS, promptControls: { ...EMPTY_PROMPT_CONTROLS } };
  }
}

export function saveGenerationPrefs(prefs: GenerationPrefs): void {
  try {
    localStorage.setItem(GENERATION_PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Private browsing — prefs live for this session only.
  }
}

export function effectivePromptControls(prefs: GenerationPrefs): PromptControlFlags {
  return resolvePromptControls(prefs.responseTemplateId, prefs.promptControls);
}

export function responseRulesActive(prefs: GenerationPrefs): boolean {
  return hasResponseRules(
    prefs.responseTemplateId,
    prefs.promptControls,
    prefs.customRulesText,
  );
}

/** Short label for the active template (shown above the composer). */
export function activeTemplateSummary(prefs: GenerationPrefs): string | null {
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

export function buildOutgoingMessage(
  userText: string,
  prefs: GenerationPrefs,
): { display: string; api: string; modelId: string; compareMode: boolean; prefs: GenerationPrefs } {
  const display = userText.trim();
  return {
    display,
    api: applyResponseTemplate(
      display,
      prefs.responseTemplateId,
      prefs.promptControls,
      prefs.customRulesText,
    ),
    modelId: prefs.modelId,
    compareMode: prefs.compareMode,
    prefs,
  };
}

/** Probe/chat generation — text rules are applied client-side to avoid double wrapping. */
export function prefsToProbeBody(prefs: GenerationPrefs) {
  const controls = effectivePromptControls(prefs);
  return {
    model: prefs.modelId,
    temperature: prefs.temperature,
    reasoning: prefs.reasoning,
    prompt_format: false,
    prompt_length: controls.length,
    prompt_stop: controls.stop,
  };
}

export function templateLabelForCompare(prefs: GenerationPrefs): string {
  if (prefs.responseTemplateId === "custom") {
    const custom = prefs.customRulesText.trim();
    if (custom) {
      const short = custom.length > 28 ? `${custom.slice(0, 28)}…` : custom;
      return `С правилами: ${short}`;
    }
    const summary = activeTemplateSummary(prefs);
    return summary ? `С шаблоном (${summary})` : "С шаблоном";
  }
  const label = templateById(prefs.responseTemplateId).label;
  return prefs.responseTemplateId === "free" ? "С шаблоном" : `Шаблон: ${label}`;
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

export { CUSTOM_RULES_MAX_CHARS, previewResponseRules } from "./promptControls";

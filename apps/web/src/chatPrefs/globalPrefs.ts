import {
  DEFAULT_GLOBAL_CHAT_PREFS,
  type ChatMode,
  type GlobalChatPrefs,
  type LanguageHint,
} from "./types";
import {
  EMPTY_PROMPT_CONTROLS,
  type PromptControlFlags,
  type ResponseTemplateId,
} from "../promptControls";

export const GLOBAL_PREFS_KEY = "aichallenge.global_chat_prefs";
const LEGACY_PREFS_KEY = "aichallenge.generation_prefs";

function inferTemplateFromControls(
  controls: PromptControlFlags,
  customRulesText: string,
): ResponseTemplateId {
  if (customRulesText.trim()) return "custom";
  if (controls.format && controls.length && controls.stop) return "structured";
  if (controls.format) return "bullets";
  if (controls.length) return "brief";
  if (controls.format || controls.length || controls.stop) return "custom";
  return "free";
}

function migrateLegacy(): GlobalChatPrefs | null {
  try {
    const raw = localStorage.getItem(LEGACY_PREFS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<{
      modelId: string;
      temperature: number;
      reasoning: boolean;
      responseTemplateId: ResponseTemplateId;
      promptControls: Partial<PromptControlFlags>;
      customRulesText: string;
      compareMode: boolean;
    }>;
    const promptControls: PromptControlFlags = {
      format: Boolean(parsed.promptControls?.format),
      length: Boolean(parsed.promptControls?.length),
      stop: Boolean(parsed.promptControls?.stop),
    };
    const customRulesText =
      typeof parsed.customRulesText === "string" ? parsed.customRulesText : "";
    const responseTemplateId =
      parsed.responseTemplateId ??
      inferTemplateFromControls(promptControls, customRulesText);
    const defaultChatMode: ChatMode = parsed.compareMode ? "compare" : "single";
    return {
      modelId: parsed.modelId ?? DEFAULT_GLOBAL_CHAT_PREFS.modelId,
      temperature:
        typeof parsed.temperature === "number"
          ? parsed.temperature
          : DEFAULT_GLOBAL_CHAT_PREFS.temperature,
      reasoning: Boolean(parsed.reasoning),
      responseTemplateId,
      promptControls,
      customRulesText,
      defaultChatMode,
      languageHint: DEFAULT_GLOBAL_CHAT_PREFS.languageHint,
    };
  } catch {
    return null;
  }
}

export function loadGlobalChatPrefs(): GlobalChatPrefs {
  try {
    const raw = localStorage.getItem(GLOBAL_PREFS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<GlobalChatPrefs>;
      const promptControls: PromptControlFlags = {
        format: Boolean(parsed.promptControls?.format),
        length: Boolean(parsed.promptControls?.length),
        stop: Boolean(parsed.promptControls?.stop),
      };
      const languageHint: LanguageHint =
        parsed.languageHint === "en" || parsed.languageHint === "ru" ? parsed.languageHint : "ru";
      const defaultChatMode: ChatMode =
        parsed.defaultChatMode === "compare" ||
        parsed.defaultChatMode === "lab" ||
        parsed.defaultChatMode === "temp_studio" ||
        parsed.defaultChatMode === "single"
          ? parsed.defaultChatMode
          : DEFAULT_GLOBAL_CHAT_PREFS.defaultChatMode;
      return {
        modelId: parsed.modelId ?? DEFAULT_GLOBAL_CHAT_PREFS.modelId,
        temperature:
          typeof parsed.temperature === "number"
            ? parsed.temperature
            : DEFAULT_GLOBAL_CHAT_PREFS.temperature,
        reasoning: Boolean(parsed.reasoning),
        responseTemplateId: parsed.responseTemplateId ?? DEFAULT_GLOBAL_CHAT_PREFS.responseTemplateId,
        promptControls,
        customRulesText:
          typeof parsed.customRulesText === "string" ? parsed.customRulesText : "",
        defaultChatMode,
        languageHint,
      };
    }
  } catch {
    // fall through to legacy / defaults
  }

  const migrated = migrateLegacy();
  if (migrated) {
    saveGlobalChatPrefs(migrated);
    return migrated;
  }

  return {
    ...DEFAULT_GLOBAL_CHAT_PREFS,
    promptControls: { ...EMPTY_PROMPT_CONTROLS },
  };
}

export function saveGlobalChatPrefs(prefs: GlobalChatPrefs): void {
  try {
    localStorage.setItem(GLOBAL_PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // private browsing
  }
}

/** Two-level chat configuration: global defaults + per-session overrides. */

import type { PromptControlFlags, ResponseTemplateId } from "../promptControls";

export type ChatMode = "single" | "compare" | "lab";

export type LanguageHint = "ru" | "en" | "";

/** Saved in localStorage — applies to every new chat until changed. */
export interface GlobalChatPrefs {
  modelId: string;
  temperature: number;
  reasoning: boolean;
  responseTemplateId: ResponseTemplateId;
  promptControls: PromptControlFlags;
  customRulesText: string;
  /** Default composer mode when opening the app or a new chat. */
  defaultChatMode: ChatMode;
  /** Soft language nudge appended to outgoing text when set. */
  languageHint: LanguageHint;
}

/** Saved in sessionStorage per chat id — overrides global for one thread. */
export interface SessionChatPrefs {
  chatMode: ChatMode;
  /** Empty string = inherit global model. */
  modelIdOverride: string;
  temperatureOverride: number | null;
  reasoningOverride: boolean | null;
  responseTemplateIdOverride: ResponseTemplateId | null;
  promptControlsOverride: PromptControlFlags | null;
  customRulesOverride: string | null;
  /** Extra instructions for every message in this chat (shown in settings preview). */
  sessionContext: string;
}

/** Merged view used by Composer and outgoing message builder. */
export interface EffectiveChatPrefs {
  modelId: string;
  temperature: number;
  reasoning: boolean;
  responseTemplateId: ResponseTemplateId;
  promptControls: PromptControlFlags;
  customRulesText: string;
  chatMode: ChatMode;
  sessionContext: string;
}

export const DEFAULT_GLOBAL_CHAT_PREFS: GlobalChatPrefs = {
  modelId: "auto",
  temperature: 0.7,
  reasoning: false,
  responseTemplateId: "free",
  promptControls: { format: false, length: false, stop: false },
  customRulesText: "",
  defaultChatMode: "single",
  languageHint: "ru",
};

export const DEFAULT_SESSION_CHAT_PREFS: SessionChatPrefs = {
  chatMode: "single",
  modelIdOverride: "",
  temperatureOverride: null,
  reasoningOverride: null,
  responseTemplateIdOverride: null,
  promptControlsOverride: null,
  customRulesOverride: null,
  sessionContext: "",
};

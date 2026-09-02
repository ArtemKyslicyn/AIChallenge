import {
  DEFAULT_SESSION_CHAT_PREFS,
  type SessionChatPrefs,
} from "./types";
import type { PromptControlFlags, ResponseTemplateId } from "../promptControls";

const KEY_PREFIX = "aichallenge.session_prefs.";

function storageKey(sessionId: string): string {
  return `${KEY_PREFIX}${sessionId}`;
}

export function loadSessionChatPrefs(sessionId: string): SessionChatPrefs {
  try {
    const raw = sessionStorage.getItem(storageKey(sessionId));
    if (!raw) {
      return { ...DEFAULT_SESSION_CHAT_PREFS, promptControlsOverride: null };
    }
    const parsed = JSON.parse(raw) as Partial<SessionChatPrefs>;
    const chatMode =
      parsed.chatMode === "compare" || parsed.chatMode === "lab" || parsed.chatMode === "single"
        ? parsed.chatMode
        : DEFAULT_SESSION_CHAT_PREFS.chatMode;

    let promptControlsOverride: PromptControlFlags | null = null;
    if (parsed.promptControlsOverride) {
      promptControlsOverride = {
        format: Boolean(parsed.promptControlsOverride.format),
        length: Boolean(parsed.promptControlsOverride.length),
        stop: Boolean(parsed.promptControlsOverride.stop),
      };
    }

    const templateOverride = parsed.responseTemplateIdOverride;
    const responseTemplateIdOverride: ResponseTemplateId | null =
      templateOverride === "free" ||
      templateOverride === "bullets" ||
      templateOverride === "brief" ||
      templateOverride === "structured" ||
      templateOverride === "custom"
        ? templateOverride
        : null;

    return {
      chatMode,
      modelIdOverride:
        typeof parsed.modelIdOverride === "string" ? parsed.modelIdOverride : "",
      temperatureOverride:
        typeof parsed.temperatureOverride === "number" ? parsed.temperatureOverride : null,
      reasoningOverride:
        typeof parsed.reasoningOverride === "boolean" ? parsed.reasoningOverride : null,
      responseTemplateIdOverride,
      promptControlsOverride,
      customRulesOverride:
        typeof parsed.customRulesOverride === "string" ? parsed.customRulesOverride : null,
      sessionContext: typeof parsed.sessionContext === "string" ? parsed.sessionContext : "",
    };
  } catch {
    return { ...DEFAULT_SESSION_CHAT_PREFS, promptControlsOverride: null };
  }
}

export function saveSessionChatPrefs(sessionId: string, prefs: SessionChatPrefs): void {
  try {
    sessionStorage.setItem(storageKey(sessionId), JSON.stringify(prefs));
  } catch {
    // private browsing
  }
}

export function initSessionChatPrefs(
  sessionId: string,
  defaultMode: SessionChatPrefs["chatMode"],
): SessionChatPrefs {
  const existing = loadSessionChatPrefs(sessionId);
  if (sessionStorage.getItem(storageKey(sessionId))) {
    return existing;
  }
  const initial = { ...DEFAULT_SESSION_CHAT_PREFS, chatMode: defaultMode };
  saveSessionChatPrefs(sessionId, initial);
  return initial;
}

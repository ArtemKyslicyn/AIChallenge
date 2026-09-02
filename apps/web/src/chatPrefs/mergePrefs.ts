import type { EffectiveChatPrefs, GlobalChatPrefs, SessionChatPrefs } from "./types";
import { resolvePromptControls } from "../promptControls";

export function mergeChatPrefs(
  global: GlobalChatPrefs,
  session: SessionChatPrefs,
): EffectiveChatPrefs {
  const responseTemplateId =
    session.responseTemplateIdOverride ?? global.responseTemplateId;
  const manualControls =
    session.promptControlsOverride ?? global.promptControls;
  const promptControls = resolvePromptControls(responseTemplateId, manualControls);

  return {
    modelId: session.modelIdOverride.trim() || global.modelId,
    temperature: session.temperatureOverride ?? global.temperature,
    reasoning: session.reasoningOverride ?? global.reasoning,
    responseTemplateId,
    promptControls,
    customRulesText: session.customRulesOverride ?? global.customRulesText,
    chatMode: session.chatMode,
    sessionContext: session.sessionContext.trim(),
  };
}

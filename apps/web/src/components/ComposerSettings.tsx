import type { ChatMode, GlobalChatPrefs, SessionChatPrefs } from "../chatPrefs/types";
import {
  CUSTOM_RULES_MAX_CHARS,
  CUSTOM_RULE_EXAMPLES,
  PROMPT_CONTROLS,
  RESPONSE_TEMPLATES,
  previewResponseRules,
  type PromptControlId,
  type ResponseTemplateId,
} from "../promptControls";

export type SettingsTab = "session";

const TAB_SESSION_ID = "settings-tab-session";
const PANEL_SESSION_ID = "settings-panel-session";

interface Props {
  tab: SettingsTab;
  onTabChange: (tab: SettingsTab) => void;
  sessionId: string;
  global: GlobalChatPrefs;
  session: SessionChatPrefs;
  onPatchGlobal: (patch: Partial<GlobalChatPrefs>) => void;
  onPatchSession: (patch: Partial<SessionChatPrefs>) => void;
  chatMode: ChatMode;
  reasoningAllowed: boolean;
  globalModelLabel: string;
  onOpenProfile?: () => void;
}

export function ComposerSettings({
  session,
  global,
  onPatchSession,
  chatMode,
  reasoningAllowed,
  globalModelLabel,
  onOpenProfile,
}: Props) {
  const activeTemplateId =
    session.responseTemplateIdOverride ?? global.responseTemplateId;
  const activeControls = session.promptControlsOverride ?? global.promptControls;
  const activeCustomRules = session.customRulesOverride ?? global.customRulesText;

  const rulesPreview = previewResponseRules(
    activeTemplateId,
    activeControls,
    activeCustomRules,
  );

  const toggleSessionControl = (id: PromptControlId) => {
    const base = session.promptControlsOverride ?? global.promptControls;
    onPatchSession({
      responseTemplateIdOverride: "custom",
      promptControlsOverride: { ...base, [id]: !base[id] },
    });
  };

  const appendSessionExample = (text: string) => {
    const current = session.customRulesOverride ?? global.customRulesText;
    onPatchSession({
      responseTemplateIdOverride: "custom",
      customRulesOverride: current.trim() ? `${current.trim()}\n${text}` : text,
    });
  };

  return (
    <div className="composer-settings">
      <p className="composer-more-lead">
        Только этот чат. Глобальные настройки —{" "}
        <button type="button" className="text-link" onClick={() => onOpenProfile?.()}>
          Подключения и модели — в профиле
        </button>
        .
      </p>

      <div
        id={PANEL_SESSION_ID}
        className="settings-panel"
        role="tabpanel"
        aria-labelledby={TAB_SESSION_ID}
      >
        <label className="composer-toggle">
          <input
            type="checkbox"
            checked={session.guestMcpEnabled}
            onChange={(e) => onPatchSession({ guestMcpEnabled: e.target.checked })}
          />
          <span>Свой сервер в этом чате</span>
        </label>

        <label className="composer-field">
          <span>Режим</span>
          <select
            value={chatMode}
            onChange={(e) => onPatchSession({ chatMode: e.target.value as ChatMode })}
          >
            <option value="single">Обычный</option>
            <option value="compare">Два рядом</option>
            <option value="temp_studio">Студия ×T</option>
            <option value="lab">Лаборатория ×4</option>
          </select>
        </label>

        <label className="composer-field">
          <span className="composer-field-row">
            <span>Контекст чата</span>
            <span className="composer-char-count">
              {session.sessionContext.length.toLocaleString()} / 800
            </span>
          </span>
          <textarea
            className="composer-rules-input"
            rows={2}
            maxLength={800}
            value={session.sessionContext}
            placeholder="Например: это учебная задача; ответь для начинающих."
            onChange={(e) => onPatchSession({ sessionContext: e.target.value })}
          />
        </label>

        <details className="settings-overrides">
          <summary>Переопределить шаблон и правила</summary>
          <div className="settings-overrides-body">
            <label className="composer-field">
              <span>Шаблон ответа</span>
              <select
                value={session.responseTemplateIdOverride ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  onPatchSession({
                    responseTemplateIdOverride: v ? (v as ResponseTemplateId) : null,
                  });
                }}
              >
                <option value="">Как в профиле ({global.responseTemplateId})</option>
                {RESPONSE_TEMPLATES.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>

            {(session.responseTemplateIdOverride ?? global.responseTemplateId) === "custom" && (
              <>
                <label className="composer-field">
                  <span>Свои правила</span>
                  <textarea
                    className="composer-rules-input"
                    rows={3}
                    maxLength={CUSTOM_RULES_MAX_CHARS}
                    value={activeCustomRules}
                    onChange={(e) => onPatchSession({ customRulesOverride: e.target.value })}
                  />
                </label>
                <div className="composer-options-chips" role="group">
                  {PROMPT_CONTROLS.map((control) => (
                    <button
                      key={control.id}
                      type="button"
                      className="control-chip"
                      aria-pressed={activeControls[control.id]}
                      onClick={() => toggleSessionControl(control.id)}
                    >
                      {control.label}
                    </button>
                  ))}
                </div>
                <div className="composer-options-chips" role="group">
                  {CUSTOM_RULE_EXAMPLES.map((example) => (
                    <button
                      key={example.label}
                      type="button"
                      className="control-chip control-chip-muted"
                      onClick={() => appendSessionExample(example.text)}
                    >
                      + {example.label}
                    </button>
                  ))}
                </div>
              </>
            )}

            {rulesPreview ? (
              <details className="composer-rules-preview">
                <summary>Как увидит модель</summary>
                <pre>{rulesPreview}</pre>
              </details>
            ) : null}
          </div>
        </details>

        <details className="settings-overrides">
          <summary>Переопределить модель и генерацию</summary>
          <div className="settings-overrides-body">
            <label className="composer-field">
              <span>Модель</span>
              <span className="composer-field-hint">Пусто = профиль ({globalModelLabel}).</span>
              {session.modelIdOverride ? (
                <button
                  type="button"
                  className="ghost-button settings-reset"
                  onClick={() => onPatchSession({ modelIdOverride: "" })}
                >
                  Сбросить → профиль
                </button>
              ) : null}
            </label>
            <label className="composer-field">
              <span>
                Температура{" "}
                {session.temperatureOverride !== null ? (
                  <strong>{session.temperatureOverride.toFixed(1)}</strong>
                ) : (
                  <span className="settings-inherited">
                    наслед. {global.temperature.toFixed(1)}
                  </span>
                )}
              </span>
              <input
                type="range"
                min={0}
                max={2}
                step={0.1}
                value={session.temperatureOverride ?? global.temperature}
                onChange={(e) =>
                  onPatchSession({ temperatureOverride: Number(e.target.value) })
                }
              />
            </label>
            <label className="composer-toggle">
              <input
                type="checkbox"
                checked={session.reasoningOverride ?? global.reasoning}
                disabled={!reasoningAllowed}
                onChange={(e) => onPatchSession({ reasoningOverride: e.target.checked })}
              />
              <span>Расширенное рассуждение в этом чате</span>
            </label>
          </div>
        </details>
      </div>
    </div>
  );
}

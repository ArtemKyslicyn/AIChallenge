import {
  CUSTOM_RULES_MAX_CHARS,
  CUSTOM_RULE_EXAMPLES,
  PROMPT_CONTROLS,
  RESPONSE_TEMPLATES,
  previewResponseRules,
  type PromptControlId,
  type ResponseTemplateId,
} from "../promptControls";
import type { ChatMode, GlobalChatPrefs, SessionChatPrefs } from "../chatPrefs/types";

type SettingsTab = "global" | "session";

interface Props {
  tab: SettingsTab;
  onTabChange: (tab: SettingsTab) => void;
  global: GlobalChatPrefs;
  session: SessionChatPrefs;
  onPatchGlobal: (patch: Partial<GlobalChatPrefs>) => void;
  onPatchSession: (patch: Partial<SessionChatPrefs>) => void;
  chatMode: ChatMode;
  reasoningAllowed: boolean;
  globalModelLabel: string;
}

export function ComposerSettings({
  tab,
  onTabChange,
  global,
  session,
  onPatchGlobal,
  onPatchSession,
  chatMode,
  reasoningAllowed,
  globalModelLabel,
}: Props) {
  const activeTemplateId =
    session.responseTemplateIdOverride ?? global.responseTemplateId;
  const activeControls =
    session.promptControlsOverride ?? global.promptControls;
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
      <div className="settings-tabs" role="tablist" aria-label="Уровень настроек">
        <button
          type="button"
          role="tab"
          className="settings-tab"
          aria-selected={tab === "global"}
          onClick={() => onTabChange("global")}
        >
          Общие
          <span className="settings-tab-hint">для всех чатов</span>
        </button>
        <button
          type="button"
          role="tab"
          className="settings-tab"
          aria-selected={tab === "session"}
          onClick={() => onTabChange("session")}
        >
          Этот чат
          <span className="settings-tab-hint">только здесь</span>
        </button>
      </div>

      {tab === "global" && (
        <div className="settings-panel" role="tabpanel">
          <p className="composer-more-lead">
            Общие настройки сохраняются в браузере и применяются к новым чатам. Их можно переопределить
            на вкладке «Этот чат».
          </p>

          <label className="composer-field">
            <span>Режим по умолчанию</span>
            <select
              value={global.defaultChatMode}
              onChange={(e) =>
                onPatchGlobal({ defaultChatMode: e.target.value as ChatMode })
              }
            >
              <option value="single">Один ответ</option>
              <option value="compare">Два рядом</option>
              <option value="lab">Лаборатория ×4</option>
            </select>
          </label>

          <label className="composer-field">
            <span>Язык ответа</span>
            <select
              value={global.languageHint || "ru"}
              onChange={(e) =>
                onPatchGlobal({
                  languageHint: e.target.value === "en" ? "en" : "ru",
                })
              }
            >
              <option value="ru">Русский</option>
              <option value="en">English</option>
            </select>
            <span className="composer-field-hint">
              Мягкая подсказка модели; не меняет язык вашего вопроса.
            </span>
          </label>

          <label className="composer-field">
            <span>Шаблон ответа по умолчанию</span>
            <select
              value={global.responseTemplateId}
              onChange={(e) =>
                onPatchGlobal({
                  responseTemplateId: e.target.value as ResponseTemplateId,
                })
              }
            >
              {RESPONSE_TEMPLATES.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
            <span className="composer-field-hint">
              {RESPONSE_TEMPLATES.find((t) => t.id === global.responseTemplateId)?.hint}
            </span>
          </label>

          {global.responseTemplateId === "custom" && (
            <GlobalCustomRules global={global} onPatchGlobal={onPatchGlobal} />
          )}

          <label className="composer-field">
            <span>
              Температура по умолчанию <strong>{global.temperature.toFixed(1)}</strong>
            </span>
            <input
              type="range"
              min={0}
              max={2}
              step={0.1}
              value={global.temperature}
              onChange={(e) => onPatchGlobal({ temperature: Number(e.target.value) })}
            />
          </label>

          <label className="composer-toggle">
            <input
              type="checkbox"
              checked={global.reasoning}
              disabled={!reasoningAllowed}
              onChange={(e) => onPatchGlobal({ reasoning: e.target.checked })}
            />
            <span>
              Расширенное рассуждение по умолчанию
              {!reasoningAllowed ? " (недоступно для модели)" : ""}
            </span>
          </label>
        </div>
      )}

      {tab === "session" && (
        <div className="settings-panel" role="tabpanel">
          <p className="composer-more-lead">
            Настройки этого чата живут, пока открыта вкладка. Смена чата или «Новый чат» — другой
            набор переопределений.
          </p>

          <label className="composer-field">
            <span>Режим для этого сообщения</span>
            <select
              value={chatMode}
              onChange={(e) => onPatchSession({ chatMode: e.target.value as ChatMode })}
            >
              <option value="single">Один ответ (SSE, сохраняется)</option>
              <option value="compare">Два рядом (probe)</option>
              <option value="lab">Лаборатория ×4 (probe)</option>
            </select>
            <span className="composer-field-hint">
              {chatMode === "single" && "Обычный диалог с сохранением в истории."}
              {chatMode === "compare" && "Два probe-ответа: без шаблона и с шаблоном."}
              {chatMode === "lab" &&
                "Четыре стратегии промпта: прямой, пошагово, meta-prompt, эксперты."}
            </span>
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
              placeholder="Например: это учебная задача по скидкам; ответь для начинающих."
              onChange={(e) => onPatchSession({ sessionContext: e.target.value })}
            />
            <span className="composer-field-hint">
              Добавляется к каждому сообщению в этом чате (видно модели, не в sidebar).
            </span>
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
                  <option value="">Как в общих ({global.responseTemplateId})</option>
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
                    <span className="composer-field-row">
                      <span>Свои правила</span>
                      <span className="composer-char-count">
                        {activeCustomRules.length.toLocaleString()} /{" "}
                        {CUSTOM_RULES_MAX_CHARS.toLocaleString()}
                      </span>
                    </span>
                    <textarea
                      className="composer-rules-input"
                      rows={3}
                      maxLength={CUSTOM_RULES_MAX_CHARS}
                      value={activeCustomRules}
                      placeholder={
                        session.customRulesOverride === null
                          ? `Наследуется из общих (${global.customRulesText.slice(0, 40) || "пусто"})…`
                          : "Правила только для этого чата"
                      }
                      onChange={(e) =>
                        onPatchSession({ customRulesOverride: e.target.value })
                      }
                    />
                    {session.customRulesOverride !== null && (
                      <button
                        type="button"
                        className="ghost-button settings-reset"
                        onClick={() => onPatchSession({ customRulesOverride: null })}
                      >
                        Сбросить к общим
                      </button>
                    )}
                  </label>

                  <div className="composer-custom-extras">
                    <span className="composer-options-label">Быстрые дополнения</span>
                    <div className="composer-options-chips" role="group">
                      {PROMPT_CONTROLS.map((control) => (
                        <button
                          key={control.id}
                          type="button"
                          className="control-chip"
                          aria-pressed={activeControls[control.id]}
                          title={control.hint}
                          onClick={() => toggleSessionControl(control.id)}
                        >
                          {control.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="composer-custom-extras">
                    <span className="composer-options-label">Примеры</span>
                    <div className="composer-options-chips" role="group">
                      {CUSTOM_RULE_EXAMPLES.map((example) => (
                        <button
                          key={example.label}
                          type="button"
                          className="control-chip control-chip-muted"
                          title={example.text}
                          onClick={() => appendSessionExample(example.text)}
                        >
                          + {example.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {rulesPreview && (
                <details className="composer-rules-preview">
                  <summary>Как увидит модель (эффективные правила)</summary>
                  <pre>{rulesPreview}</pre>
                </details>
              )}
            </div>
          </details>

          <details className="settings-overrides">
            <summary>Переопределить модель и генерацию</summary>
            <div className="settings-overrides-body">
              <label className="composer-field">
                <span>Модель</span>
                <span className="composer-field-hint">
                  Выберите в панели над полем ввода. Пустое переопределение = «Общие: {globalModelLabel}».
                </span>
                {session.modelIdOverride ? (
                  <button
                    type="button"
                    className="ghost-button settings-reset"
                    onClick={() => onPatchSession({ modelIdOverride: "" })}
                  >
                    Сбросить модель ({session.modelIdOverride}) → общие
                  </button>
                ) : (
                  <span className="settings-inherited">Сейчас: общие ({globalModelLabel})</span>
                )}
              </label>

              <label className="composer-field">
                <span>
                  Температура{" "}
                  {session.temperatureOverride !== null ? (
                    <strong>{session.temperatureOverride.toFixed(1)}</strong>
                  ) : (
                    <span className="settings-inherited">наслед. {global.temperature.toFixed(1)}</span>
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
                {session.temperatureOverride !== null && (
                  <button
                    type="button"
                    className="ghost-button settings-reset"
                    onClick={() => onPatchSession({ temperatureOverride: null })}
                  >
                    Как в общих
                  </button>
                )}
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
              {session.reasoningOverride !== null && (
                <button
                  type="button"
                  className="ghost-button settings-reset"
                  onClick={() => onPatchSession({ reasoningOverride: null })}
                >
                  Рассуждение: как в общих
                </button>
              )}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

function GlobalCustomRules({
  global,
  onPatchGlobal,
}: {
  global: GlobalChatPrefs;
  onPatchGlobal: (patch: Partial<GlobalChatPrefs>) => void;
}) {
  const toggle = (id: PromptControlId) => {
    onPatchGlobal({
      responseTemplateId: "custom",
      promptControls: { ...global.promptControls, [id]: !global.promptControls[id] },
    });
  };

  return (
    <div className="composer-custom-rules">
      <label className="composer-field">
        <span className="composer-field-row">
          <span>Правила по умолчанию</span>
          <span className="composer-char-count">
            {global.customRulesText.length.toLocaleString()} / {CUSTOM_RULES_MAX_CHARS.toLocaleString()}
          </span>
        </span>
        <textarea
          className="composer-rules-input"
          rows={3}
          maxLength={CUSTOM_RULES_MAX_CHARS}
          value={global.customRulesText}
          onChange={(e) =>
            onPatchGlobal({ responseTemplateId: "custom", customRulesText: e.target.value })
          }
        />
      </label>
      <div className="composer-custom-extras">
        <span className="composer-options-label">Быстрые дополнения</span>
        <div className="composer-options-chips" role="group">
          {PROMPT_CONTROLS.map((control) => (
            <button
              key={control.id}
              type="button"
              className="control-chip"
              aria-pressed={global.promptControls[control.id]}
              onClick={() => toggle(control.id)}
            >
              {control.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

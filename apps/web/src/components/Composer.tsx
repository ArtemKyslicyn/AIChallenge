import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { listModels, type ModelCatalogItemDto } from "../api/client";
import {
  activeTemplateSummary,
  buildOutgoingMessage,
  CUSTOM_RULES_MAX_CHARS,
  loadGenerationPrefs,
  previewResponseRules,
  responseRulesActive,
  saveGenerationPrefs,
  type GenerationPrefs,
} from "../generationPrefs";
import {
  CUSTOM_RULE_EXAMPLES,
  PROMPT_CONTROLS,
  RESPONSE_TEMPLATES,
  type PromptControlId,
  type ResponseTemplateId,
} from "../promptControls";

export interface OutgoingMessage {
  /** Shown in the thread — the user's own wording. */
  display: string;
  /** Sent to the API — may include response-shape rules. */
  api: string;
  /** Model pin for this reply (`auto` = router chain). */
  modelId: string;
  /** Side-by-side compare in the thread (probe, not saved as chat rows). */
  compareMode: boolean;
  prefs: GenerationPrefs;
}

interface Props {
  onSend: (message: OutgoingMessage) => void;
  onStop: () => void;
  busy: boolean;
  maxChars: number;
  seed: { text: string; nonce: number } | null;
}

const MAX_HEIGHT = 200;

export function Composer({ onSend, onStop, busy, maxChars, seed }: Props) {
  const [value, setValue] = useState("");
  const [prefs, setPrefs] = useState<GenerationPrefs>(() => loadGenerationPrefs());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [models, setModels] = useState<ModelCatalogItemDto[]>([]);
  const box = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    if (seed) setValue(seed.text);
  }, [seed]);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  useEffect(() => {
    listModels().then(setModels).catch(() => setModels([]));
  }, []);

  const patchPrefs = useCallback((patch: Partial<GenerationPrefs>) => {
    setPrefs((prev) => {
      const next = { ...prev, ...patch };
      saveGenerationPrefs(next);
      return next;
    });
  }, []);

  const toggleControl = (id: PromptControlId) => {
    patchPrefs({
      responseTemplateId: "custom",
      promptControls: {
        ...prefs.promptControls,
        [id]: !prefs.promptControls[id],
      },
    });
  };

  const trimmed = value.trim();
  const outgoing = buildOutgoingMessage(trimmed, prefs);
  const tooLong = outgoing.api.length > maxChars;
  const canSend = Boolean(trimmed) && !busy && !tooLong;
  const templateSummary = activeTemplateSummary(prefs);
  const rulesPreview = previewResponseRules(
    prefs.responseTemplateId,
    prefs.promptControls,
    prefs.customRulesText,
  );
  const customRulesLen = prefs.customRulesText.length;
  const rulesMissing =
    prefs.compareMode &&
    prefs.responseTemplateId === "custom" &&
    !responseRulesActive(prefs);
  const selectedModel = models.find((m) => m.id === prefs.modelId);
  const reasoningAllowed = selectedModel?.capabilities.reasoning ?? true;
  const modelOptions =
    models.length > 0
      ? models
      : [{ id: "auto", label: "Авто (цепочка)", capabilities: { reasoning: false } }];

  const appendExample = (text: string) => {
    patchPrefs({
      responseTemplateId: "custom",
      customRulesText: prefs.customRulesText.trim()
        ? `${prefs.customRulesText.trim()}\n${text}`
        : text,
    });
  };

  function submit() {
    if (!canSend) return;
    onSend(outgoing);
    setValue("");
  }

  return (
    <div className="composer-wrap">
      {tooLong && (
        <p className="alert" role="alert">
          <strong>Слишком длинно.</strong> {outgoing.api.length.toLocaleString()} из{" "}
          {maxChars.toLocaleString()} символов
          {templateSummary ? " (с учётом шаблона)" : ""}.
        </p>
      )}

      <div className="composer-shell">
        <div className="composer-options-bar">
          <label className="composer-model-picker">
            <span className="composer-options-label">Модель</span>
            <select
              className="composer-model-select"
              value={prefs.modelId}
              onChange={(e) => patchPrefs({ modelId: e.target.value })}
              aria-label="Модель ответа"
            >
              {modelOptions.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>

          <span className="composer-options-label">Режим</span>
          <div className="composer-mode-toggle" role="group" aria-label="Режим ответа">
            <button
              type="button"
              className="mode-chip"
              aria-pressed={!prefs.compareMode}
              onClick={() => patchPrefs({ compareMode: false })}
            >
              Один
            </button>
            <button
              type="button"
              className="mode-chip"
              aria-pressed={prefs.compareMode}
              onClick={() => patchPrefs({ compareMode: true })}
            >
              Два рядом
            </button>
          </div>

          <button
            type="button"
            className="ghost-button composer-more-toggle"
            aria-expanded={settingsOpen}
            onClick={() => setSettingsOpen((open) => !open)}
          >
            {settingsOpen ? "Скрыть" : "Настройки"}
          </button>
        </div>

        {(templateSummary || prefs.compareMode || rulesMissing) && (
          <p className={`composer-options-hint${rulesMissing ? " composer-options-warn" : ""}`}>
            {rulesMissing
              ? "Режим «Два рядом»: добавьте текст правил или быстрые дополнения — иначе ответы совпадут."
              : prefs.compareMode
                ? "Два ответа рядом: без шаблона и с шаблоном"
                : "Следующее сообщение"}
            {!rulesMissing && templateSummary ? `: ${templateSummary}` : ""}
            {!rulesMissing && prefs.compareMode && !templateSummary ? " · шаблон «Свободный»" : ""}
          </p>
        )}

        {settingsOpen && (
          <div className="composer-more">
            <p className="composer-more-lead">
              Шаблон задаёт формат ответа. В режиме «Два рядом» сравниваются свободный ответ и ответ
              с выбранным шаблоном.
            </p>

            <label className="composer-field">
              <span>Шаблон ответа</span>
              <select
                value={prefs.responseTemplateId}
                onChange={(e) =>
                  patchPrefs({ responseTemplateId: e.target.value as ResponseTemplateId })
                }
              >
                {RESPONSE_TEMPLATES.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))}
              </select>
              <span className="composer-field-hint">
                {RESPONSE_TEMPLATES.find((t) => t.id === prefs.responseTemplateId)?.hint}
              </span>
            </label>

            {prefs.responseTemplateId === "custom" && (
              <div className="composer-custom-rules">
                <label className="composer-field">
                  <span className="composer-field-row">
                    <span>Правила для модели</span>
                    <span className="composer-char-count" aria-live="polite">
                      {customRulesLen.toLocaleString()} / {CUSTOM_RULES_MAX_CHARS.toLocaleString()}
                    </span>
                  </span>
                  <textarea
                    className="composer-rules-input"
                    rows={3}
                    value={prefs.customRulesText}
                    maxLength={CUSTOM_RULES_MAX_CHARS}
                    placeholder="Например: ответь тремя пунктами; без вступления; закончи строкой «Готово»."
                    aria-describedby="custom-rules-hint"
                    onChange={(e) =>
                      patchPrefs({
                        responseTemplateId: "custom",
                        customRulesText: e.target.value,
                      })
                    }
                  />
                  <span id="custom-rules-hint" className="composer-field-hint">
                    Этот текст увидит модель после вашего вопроса. Можно комбинировать с быстрыми
                    дополнениями ниже.
                  </span>
                </label>

                <div className="composer-custom-extras">
                  <span className="composer-options-label">Быстрые дополнения</span>
                  <div className="composer-options-chips" role="group" aria-label="Быстрые правила">
                    {PROMPT_CONTROLS.map((control) => (
                      <button
                        key={control.id}
                        type="button"
                        className="control-chip"
                        aria-pressed={prefs.promptControls[control.id]}
                        title={control.hint}
                        onClick={() => toggleControl(control.id)}
                      >
                        {control.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="composer-custom-extras">
                  <span className="composer-options-label">Примеры фраз</span>
                  <div className="composer-options-chips" role="group" aria-label="Примеры правил">
                    {CUSTOM_RULE_EXAMPLES.map((example) => (
                      <button
                        key={example.label}
                        type="button"
                        className="control-chip control-chip-muted"
                        title={example.text}
                        onClick={() => appendExample(example.text)}
                      >
                        + {example.label}
                      </button>
                    ))}
                  </div>
                </div>

                {rulesPreview && (
                  <details className="composer-rules-preview">
                    <summary>Как увидит модель</summary>
                    <pre>{rulesPreview}</pre>
                  </details>
                )}
              </div>
            )}

            <label className="composer-field">
              <span>
                Температура <strong>{prefs.temperature.toFixed(1)}</strong>
              </span>
              <input
                type="range"
                min={0}
                max={2}
                step={0.1}
                value={prefs.temperature}
                onChange={(e) => patchPrefs({ temperature: Number(e.target.value) })}
              />
            </label>

            <label className="composer-toggle">
              <input
                type="checkbox"
                checked={prefs.reasoning}
                disabled={!reasoningAllowed}
                onChange={(e) => patchPrefs({ reasoning: e.target.checked })}
              />
              <span>Расширенное рассуждение{!reasoningAllowed ? " (недоступно)" : ""}</span>
            </label>
          </div>
        )}

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <textarea
            ref={box}
            rows={1}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={
              prefs.compareMode
                ? "Сообщение для сравнения двух ответов…"
                : "Напишите сообщение…"
            }
            aria-label="Сообщение"
          />

          {busy ? (
            <button
              type="button"
              className="icon-button"
              data-variant="stop"
              onClick={onStop}
              aria-label="Остановить генерацию"
              title="Остановить генерацию"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                <rect width="12" height="12" rx="2.5" fill="currentColor" />
              </svg>
            </button>
          ) : (
            <button
              type="submit"
              className="icon-button"
              disabled={!canSend}
              aria-label="Отправить сообщение"
              title="Отправить"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M12 20V5m0 0-6 6m6-6 6 6"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          )}
        </form>
      </div>

      <p className="hint">
        <kbd>Enter</kbd> — отправить · <kbd>Shift</kbd>+<kbd>Enter</kbd> — новая строка
      </p>
    </div>
  );
}

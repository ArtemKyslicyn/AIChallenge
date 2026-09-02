import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { listLabPresets, listModels, type LabPresetDto, type ModelCatalogItemDto } from "../api/client";
import {
  initSessionChatPrefs,
  loadGlobalChatPrefs,
  mergeChatPrefs,
  saveGlobalChatPrefs,
  saveSessionChatPrefs,
  type ChatMode,
  type EffectiveChatPrefs,
  type GlobalChatPrefs,
  type SessionChatPrefs,
} from "../chatPrefs";
import { buildOutgoingMessage } from "../chatPrefs/outgoing";
import { activeTemplateSummary } from "../generationPrefs";
import { hasResponseRules } from "../promptControls";
import { ComposerSettings } from "./ComposerSettings";

export interface OutgoingMessage {
  display: string;
  api: string;
  modelId: string;
  chatMode: ChatMode;
  effective: EffectiveChatPrefs;
  labMeta?: { goldenAnswer?: string; rubric?: string; presetId?: string };
}

interface Props {
  sessionId: string;
  onSend: (message: OutgoingMessage) => void;
  onStop: () => void;
  busy: boolean;
  maxChars: number;
  seed: { text: string; nonce: number } | null;
}

const MAX_HEIGHT = 200;

const LAB_SUGGESTION =
  "В магазине акция: при покупке от 3 товаров скидка 10% на каждый. Товар стоит 400 ₽. Клиент покупает ровно 4 штуки. Сколько заплатит? Покажите расчёт.";

export function Composer({ sessionId, onSend, onStop, busy, maxChars, seed }: Props) {
  const [value, setValue] = useState("");
  const [global, setGlobal] = useState<GlobalChatPrefs>(() => loadGlobalChatPrefs());
  const [session, setSession] = useState<SessionChatPrefs>(() =>
    initSessionChatPrefs(sessionId, loadGlobalChatPrefs().defaultChatMode),
  );
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<"global" | "session">("global");
  const [models, setModels] = useState<ModelCatalogItemDto[]>([]);
  const [labPresets, setLabPresets] = useState<LabPresetDto[]>([]);
  const [labPresetId, setLabPresetId] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setSession(initSessionChatPrefs(sessionId, global.defaultChatMode));
  }, [sessionId, global.defaultChatMode]);

  const effective = useMemo(() => mergeChatPrefs(global, session), [global, session]);

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
    listLabPresets().then(setLabPresets).catch(() => setLabPresets([]));
  }, []);

  const patchGlobal = useCallback((patch: Partial<GlobalChatPrefs>) => {
    setGlobal((prev) => {
      const next = { ...prev, ...patch };
      saveGlobalChatPrefs(next);
      return next;
    });
  }, []);

  const patchSession = useCallback(
    (patch: Partial<SessionChatPrefs>) => {
      setSession((prev) => {
        const next = { ...prev, ...patch };
        saveSessionChatPrefs(sessionId, next);
        return next;
      });
    },
    [sessionId],
  );

  const setChatMode = useCallback(
    (chatMode: ChatMode) => patchSession({ chatMode }),
    [patchSession],
  );

  const trimmed = value.trim();
  const manualControls =
    session.promptControlsOverride ?? global.promptControls;
  const outgoing = buildOutgoingMessage(trimmed, effective, global, manualControls);
  const tooLong = outgoing.api.length > maxChars;
  const canSend = Boolean(trimmed) && !busy && !tooLong;
  const templateSummary = activeTemplateSummary({
    responseTemplateId: effective.responseTemplateId,
    promptControls: effective.promptControls,
    customRulesText: effective.customRulesText,
  });
  const rulesMissing =
    effective.chatMode === "compare" &&
    effective.responseTemplateId === "custom" &&
    !hasResponseRules(
      effective.responseTemplateId,
      effective.promptControls,
      effective.customRulesText,
    );

  const modelOptions =
    models.length > 0
      ? models
      : [{ id: "auto", label: "Авто (цепочка)", capabilities: { reasoning: false } }];

  const selectedModel = modelOptions.find((m) => m.id === effective.modelId);
  const reasoningAllowed = selectedModel?.capabilities.reasoning ?? true;
  const globalModelLabel =
    modelOptions.find((m) => m.id === global.modelId)?.label ?? global.modelId;

  function submit() {
    if (!canSend) return;
    const preset = labPresets.find((p) => p.id === labPresetId);
    onSend({
      display: outgoing.display,
      api: outgoing.api,
      modelId: outgoing.modelId,
      chatMode: effective.chatMode,
      effective,
      labMeta:
        effective.chatMode === "lab"
          ? {
              goldenAnswer: preset?.golden_answer,
              rubric: preset?.rubric,
              presetId: preset?.id,
            }
          : undefined,
    });
    setValue("");
  }

  const modeHint =
    effective.chatMode === "lab"
      ? "Четыре стратегии промпта параллельно"
      : effective.chatMode === "compare"
        ? "Два ответа: без шаблона и с шаблоном"
        : templateSummary
          ? `Шаблон: ${templateSummary}`
          : null;

  const placeholder =
    effective.chatMode === "lab"
      ? "Задача для лаборатории (логика, расчёт, анализ)…"
      : effective.chatMode === "compare"
        ? "Сообщение для сравнения двух ответов…"
        : "Напишите сообщение…";

  return (
    <div className="composer-wrap">
      {tooLong && (
        <p className="alert" role="alert">
          <strong>Слишком длинно.</strong> {outgoing.api.length.toLocaleString()} из{" "}
          {maxChars.toLocaleString()} символов
          {templateSummary || effective.sessionContext ? " (с учётом правил и контекста)" : ""}.
        </p>
      )}

      <div className="composer-shell">
        <div className="composer-options-bar">
          <label className="composer-model-picker">
            <span className="composer-options-label">Модель</span>
            <select
              className="composer-model-select"
              value={session.modelIdOverride}
              onChange={(e) => {
                patchSession({ modelIdOverride: e.target.value });
                if (e.target.value) setSettingsTab("session");
              }}
              aria-label="Модель ответа"
            >
              <option value="">Общие: {globalModelLabel}</option>
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
              aria-pressed={effective.chatMode === "single"}
              onClick={() => setChatMode("single")}
            >
              Один
            </button>
            <button
              type="button"
              className="mode-chip"
              aria-pressed={effective.chatMode === "compare"}
              onClick={() => setChatMode("compare")}
            >
              ×2
            </button>
            <button
              type="button"
              className="mode-chip mode-chip-lab"
              aria-pressed={effective.chatMode === "lab"}
              onClick={() => setChatMode("lab")}
              title="Лаборатория: 4 стратегии промпта"
            >
              ×4
            </button>
          </div>

          {effective.chatMode === "lab" && labPresets.length > 0 && (
            <label className="composer-model-picker composer-lab-preset">
              <span className="composer-options-label">Пресет</span>
              <select
                className="composer-model-select"
                value={labPresetId}
                aria-label="Пресет задачи лаборатории"
                onChange={(e) => {
                  const id = e.target.value;
                  setLabPresetId(id);
                  const preset = labPresets.find((p) => p.id === id);
                  if (preset) setValue(preset.task);
                }}
              >
                <option value="">Своя задача</option>
                {labPresets.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
              </select>
            </label>
          )}

          {effective.chatMode === "lab" && !trimmed && !labPresetId && (
            <button
              type="button"
              className="ghost-button composer-lab-sample"
              onClick={() => setValue(LAB_SUGGESTION)}
            >
              Пример задачи
            </button>
          )}

          <button
            type="button"
            className="ghost-button composer-more-toggle"
            aria-expanded={settingsOpen}
            onClick={() => setSettingsOpen((open) => !open)}
          >
            {settingsOpen ? "Скрыть" : "Настройки"}
          </button>
        </div>

        {(modeHint || rulesMissing || effective.sessionContext) && (
          <p className={`composer-options-hint${rulesMissing ? " composer-options-warn" : ""}`}>
            {rulesMissing
              ? "Режим «×2»: задайте правила шаблона — иначе ответы совпадут."
              : modeHint}
            {effective.sessionContext && !rulesMissing
              ? ` · контекст чата (${effective.sessionContext.length} симв.)`
              : ""}
          </p>
        )}

        {settingsOpen && (
          <ComposerSettings
            tab={settingsTab}
            onTabChange={setSettingsTab}
            global={global}
            session={session}
            onPatchGlobal={patchGlobal}
            onPatchSession={patchSession}
            chatMode={effective.chatMode}
            reasoningAllowed={reasoningAllowed}
            globalModelLabel={globalModelLabel}
          />
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
            placeholder={placeholder}
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
        {effective.chatMode === "lab" ? " · ×4 не сохраняется в истории сервера" : ""}
      </p>
    </div>
  );
}

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
import {
  TEMP_STUDIO_PRESETS,
  clampTemp,
  formatTemp,
  matchPresetId,
  normalizeTempTriple,
} from "../strategies/tempStudio";
import { ComposerSettings } from "./ComposerSettings";

export interface OutgoingMessage {
  display: string;
  api: string;
  modelId: string;
  chatMode: ChatMode;
  effective: EffectiveChatPrefs;
  labMeta?: { goldenAnswer?: string; rubric?: string; presetId?: string };
  /** Three temperatures for ×T (ignored in other modes). */
  tempStudioTemps?: [number, number, number];
}

export type ComposerSeed = {
  text: string;
  nonce: number;
  /** Force chat mode when seeding (e.g. media chips → single). */
  chatMode?: ChatMode;
};

interface Props {
  sessionId: string;
  onSend: (message: OutgoingMessage) => void;
  onStop: () => void;
  busy: boolean;
  maxChars: number;
  seed: ComposerSeed | null;
}

const MAX_HEIGHT = 200;

const LAB_SUGGESTION =
  "В магазине акция: при покупке от 3 товаров скидка 10% на каждый. Товар стоит 400 ₽. Клиент покупает ровно 4 штуки. Сколько заплатит? Покажите расчёт.";

/**
 * Client-side media intent — mirrors `media_tools.detect_media_intent` hard hints
 * (_COMIC_HINT / _IMAGE_HINT / _VIDEO_HINT), not the soft gate alone.
 * Bare «сгенерируй…» without a media noun does not force single.
 */
function looksLikeMediaIntent(text: string): boolean {
  const t = text.trim();
  if (!t) return false;
  const comic =
    /комикс|comic\s*strip|(?:нарисуй|сделай|сгенер(?:ируй|ировать))\s+комикс|(?:draw|make|create|generate)\s+(?:a\s+)?comic/i;
  const image =
    /нарисуй|сгенер(?:ируй|ировать)\s+(?:картинк|изображен)|сделай\s+(?:мне\s+)?(?:картинк|изображен|рисунок)|хочу\s+(?:картинк|изображен|рисунок)|(?:generate|draw|paint|create)\s+(?:an?\s+)?(?:image|picture|drawing)|\/pollinations\b/i;
  const video =
    /сделай\s+(?:коротк\w+\s+)?видео|сгенер(?:ируй|ировать)\s+видео|(?:generate|make|create)\s+(?:a\s+)?(?:short\s+)?video|\/pixazo\b/i;
  return comic.test(t) || image.test(t) || video.test(t);
}

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
  const [forceSingleHint, setForceSingleHint] = useState<string | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const forceHintTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // The composer is sticky and its height changes a lot: the options bar wraps,
  // ×4 adds a preset row, «Настройки» opens a whole panel, the textarea grows.
  // Publish the measured height as `--composer-h` so `.float-dock` can sit
  // above it instead of guessing (index.css keeps a fallback for the first
  // frame). No React state — this must not re-render the thread on every
  // keystroke that grows the textarea.
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const root = document.documentElement;
    const publish = () => {
      root.style.setProperty("--composer-h", `${Math.ceil(el.getBoundingClientRect().height)}px`);
    };
    publish();
    const observer = new ResizeObserver(publish);
    observer.observe(el);
    return () => {
      observer.disconnect();
      root.style.removeProperty("--composer-h");
    };
  }, []);

  useEffect(() => {
    setSession(initSessionChatPrefs(sessionId, global.defaultChatMode));
  }, [sessionId, global.defaultChatMode]);

  const effective = useMemo(() => mergeChatPrefs(global, session), [global, session]);

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
    (chatMode: ChatMode) => {
      patchSession({ chatMode });
    },
    [patchSession],
  );

  useLayoutEffect(() => {
    if (!seed) return;
    setValue(seed.text);
    if (seed.chatMode) {
      patchSession({ chatMode: seed.chatMode });
    }
    requestAnimationFrame(() => box.current?.focus());
  }, [seed, patchSession]);

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

  useEffect(() => {
    return () => {
      if (forceHintTimer.current) clearTimeout(forceHintTimer.current);
    };
  }, []);

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

  function applyMediaDraft(kind: "image" | "video") {
    setChatMode("single");
    const prefixes = {
      image: "Нарисуй ",
      video: "Сделай короткое видео: ",
    } as const;
    const prefix = prefixes[kind];
    setValue((prev) => {
      const t = prev.trim();
      if (!t) return prefix;

      if (kind === "image") {
        const videoPrefixed = t.match(
          /^(?:сделай\s+короткое\s+видео\s*:?\s*|сгенерируй\s+(?:короткое\s+)?видео\s*:?\s*)([\s\S]*)$/i,
        );
        if (videoPrefixed) {
          const rest = videoPrefixed[1].trim();
          return rest ? `Нарисуй ${rest}` : "Нарисуй ";
        }
        if (/^(нарисуй|сгенерируй)\b/i.test(t)) return prev;
        if (/^сделай\b/i.test(t)) {
          const rest = t.replace(/^сделай\b\s*/i, "").trim();
          return rest ? `Нарисуй ${rest}` : "Нарисуй ";
        }
        return `${prefix}${t}`;
      }

      const imagePrefixed = t.match(/^(?:нарисуй|сгенерируй)\b\s*/i);
      if (imagePrefixed) {
        const rest = t.slice(imagePrefixed[0].length).trim();
        return rest ? `Сделай короткое видео: ${rest}` : "Сделай короткое видео: ";
      }
      if (/^(сделай|сгенерируй)\b/i.test(t)) return prev;
      return `${prefix}${t}`;
    });
    requestAnimationFrame(() => box.current?.focus());
  }

  function submit() {
    if (!canSend) return;
    const forceSingle = effective.chatMode !== "single" && looksLikeMediaIntent(trimmed);
    const chatMode: ChatMode = forceSingle ? "single" : effective.chatMode;
    if (forceSingle) {
      setChatMode("single");
      setForceSingleHint("Медиа → обычный чат");
      if (forceHintTimer.current) clearTimeout(forceHintTimer.current);
      forceHintTimer.current = setTimeout(() => setForceSingleHint(null), 4000);
    }
    const prefs = forceSingle ? { ...effective, chatMode: "single" as const } : effective;
    const preset = labPresets.find((p) => p.id === labPresetId);
    onSend({
      display: outgoing.display,
      api: outgoing.api,
      modelId: outgoing.modelId,
      chatMode,
      effective: prefs,
      labMeta:
        chatMode === "lab"
          ? {
              goldenAnswer: preset?.golden_answer,
              rubric: preset?.rubric,
              presetId: preset?.id,
            }
          : undefined,
      tempStudioTemps:
        chatMode === "temp_studio"
          ? normalizeTempTriple(session.tempStudioTemps)
          : undefined,
    });
    setValue("");
  }

  const studioTemps = normalizeTempTriple(session.tempStudioTemps);
  const studioPreset = matchPresetId(studioTemps);

  function setStudioTempAt(index: 0 | 1 | 2, value: number) {
    const next: [number, number, number] = [...studioTemps];
    next[index] = clampTemp(value);
    patchSession({ tempStudioTemps: next });
  }

  const modeHint =
    effective.chatMode === "lab"
      ? "Четыре способа задать один вопрос"
      : effective.chatMode === "temp_studio"
        ? `Один запрос — три тона ответа (t = ${studioTemps.map(formatTemp).join(" · ")})`
        : effective.chatMode === "compare"
          ? "Два ответа: без шаблона и с шаблоном"
          : templateSummary
            ? `Шаблон: ${templateSummary}`
            : null;

  const placeholder =
    effective.chatMode === "lab"
      ? "Задача: сравним четыре способа ответа…"
      : effective.chatMode === "temp_studio"
        ? "Один текст — три ответа разным тоном…"
        : effective.chatMode === "compare"
          ? "Сообщение — сравним два ответа…"
          : "Напишите сообщение…";

  return (
    <div className="composer-wrap" ref={wrap}>
      {tooLong && (
        <p className="alert" role="alert">
          <strong>Слишком длинно.</strong> {outgoing.api.length.toLocaleString()} из{" "}
          {maxChars.toLocaleString()} символов
          {templateSummary || effective.sessionContext ? " (с учётом правил и контекста)" : ""}.
        </p>
      )}

      <div className="composer-shell">
        <div className="composer-options-bar">
          <label className="composer-model-picker" htmlFor="composer-model-select">
            <span className="composer-options-label">Модель</span>
            <select
              id="composer-model-select"
              className="composer-model-select"
              value={session.modelIdOverride}
              onChange={(e) => {
                patchSession({ modelIdOverride: e.target.value });
                if (e.target.value) setSettingsTab("session");
              }}
            >
              <option value="">Общие: {globalModelLabel}</option>
              {modelOptions.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>

          <div className="composer-mode-toggle" role="group" aria-label="Режим ответа">
            <button
              type="button"
              className="mode-chip mode-chip-stack mode-chip-default"
              aria-pressed={effective.chatMode === "single"}
              aria-label="Обычный чат — один ответ, под ним видно модель"
              onClick={() => setChatMode("single")}
              title="Один ответ · под ним видно модель"
            >
              <span className="mode-chip-kicker">Чат</span>
              <span className="mode-chip-label">Обычный</span>
            </button>
            <button
              type="button"
              className="mode-chip mode-chip-stack"
              aria-pressed={effective.chatMode === "compare"}
              aria-label="×2 — два ответа: без правил и с правилами"
              onClick={() => setChatMode("compare")}
              title="Два ответа: без правил и с правилами"
            >
              <span className="mode-chip-kicker">Шаблоны</span>
              <span className="mode-chip-label">×2</span>
            </button>
            <button
              type="button"
              className="mode-chip mode-chip-stack mode-chip-temp"
              aria-pressed={effective.chatMode === "temp_studio"}
              aria-label="×T — один текст, три ответа разной смелости"
              onClick={() => setChatMode("temp_studio")}
              title="Один текст — три ответа разной «смелости»"
            >
              <span className="mode-chip-kicker">Темп.</span>
              <span className="mode-chip-label">×T</span>
            </button>
            <button
              type="button"
              className="mode-chip mode-chip-stack mode-chip-lab"
              aria-pressed={effective.chatMode === "lab"}
              aria-label="×4 — один вопрос, четыре способа спросить"
              onClick={() => setChatMode("lab")}
              title="Один вопрос — четыре способа спросить"
            >
              <span className="mode-chip-kicker">Лаб</span>
              <span className="mode-chip-label">×4</span>
            </button>
          </div>

          <div className="composer-media-actions" role="group" aria-label="Медиа">
            <button
              type="button"
              className="composer-media-btn"
              disabled={busy}
              onClick={() => applyMediaDraft("image")}
              aria-label="Подставить черновик: Нарисуй… (режим обычный чат)"
              title="Обычный чат + «Нарисуй…»"
            >
              Картинка
            </button>
            <button
              type="button"
              className="composer-media-btn composer-media-btn--quiet"
              disabled={busy}
              onClick={() => applyMediaDraft("video")}
              aria-label="Подставить черновик запроса на видео (режим обычный чат)"
              title="Обычный чат + запрос на видео"
            >
              Видео
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
            aria-controls="composer-settings-panel"
            onClick={() => setSettingsOpen((open) => !open)}
          >
            {settingsOpen ? "Скрыть" : "Настройки"}
          </button>
        </div>

        {effective.chatMode === "temp_studio" && (
          <div
            className="composer-temp-bar"
            role="group"
            aria-label="Температуры студии ×T"
          >
            <label className="composer-model-picker composer-temp-preset">
              <span className="composer-options-label">Пресет t</span>
              <select
                className="composer-model-select"
                value={studioPreset}
                aria-label="Пресет температур"
                onChange={(e) => {
                  const id = e.target.value;
                  const preset = TEMP_STUDIO_PRESETS.find((p) => p.id === id);
                  if (preset) patchSession({ tempStudioTemps: [...preset.temps] });
                }}
              >
                {TEMP_STUDIO_PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
                <option value="custom" disabled={studioPreset !== "custom"}>
                  Свои значения
                </option>
              </select>
            </label>
            {([0, 1, 2] as const).map((i) => (
              <label key={i} className="composer-temp-field">
                <span className="composer-options-label">
                  {i === 0 ? "Низкая" : i === 1 ? "Средняя" : "Высокая"}
                </span>
                <input
                  type="number"
                  className="composer-temp-input"
                  min={0}
                  max={2}
                  step={0.1}
                  value={studioTemps[i]}
                  aria-label={
                    i === 0 ? "Низкая температура" : i === 1 ? "Средняя температура" : "Высокая температура"
                  }
                  onChange={(e) => setStudioTempAt(i, Number(e.target.value))}
                />
              </label>
            ))}
          </div>
        )}

        {(forceSingleHint || modeHint || rulesMissing || effective.sessionContext) && (
          <p
            id={rulesMissing ? "composer-rules-warn" : undefined}
            role={rulesMissing ? "alert" : forceSingleHint ? "status" : undefined}
            className={`composer-options-hint${rulesMissing ? " composer-options-warn" : ""}`}
          >
            {rulesMissing
              ? "Режим «×2»: задайте правила шаблона — иначе ответы совпадут."
              : forceSingleHint
                ? forceSingleHint
                : modeHint}
            {effective.sessionContext && !rulesMissing && !forceSingleHint
              ? ` · контекст чата (${effective.sessionContext.length} симв.)`
              : ""}
          </p>
        )}

        {settingsOpen && (
          <div id="composer-settings-panel">
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
            id="composer-message"
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
            aria-invalid={rulesMissing || undefined}
            aria-describedby={
              [rulesMissing ? "composer-rules-warn" : null, "composer-keyboard-hint"]
                .filter(Boolean)
                .join(" ") || undefined
            }
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

      <p className="hint" id="composer-keyboard-hint">
        <kbd>Enter</kbd> — отправить · <kbd>Shift</kbd>+<kbd>Enter</kbd> — новая строка
        {effective.chatMode === "single"
          ? " · для картинки: кнопка «Картинка» или «нарисуй…»"
          : " · «Картинка» переключит на обычный чат"}
        {effective.chatMode === "lab" || effective.chatMode === "temp_studio"
          ? " · этот режим не пишется в историю чата"
          : ""}
      </p>
    </div>
  );
}

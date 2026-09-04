import { useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from "react";

import {
  MAX_MESSAGE_CHARS,
  isNotFound,
  listMessages,
  probeComplete,
  sendMessageSSE,
  type ChatEvent,
  type MessageDto,
  type SessionCredentials,
} from "../api/client";
import { prefsToProbeBody } from "../chatPrefs/outgoing";
import { useDebugLog } from "../debug/DebugContext";
import { countWords } from "../generationPrefs";
import {
  PROMPT_STRATEGY_IDS,
  runLabJudge,
  runPromptStrategy,
} from "../strategies";
import type { PromptStrategyId } from "../strategies/types";
import type { MediaJobState, ThreadItem, Turn } from "../types";
import {
  EMPTY_PROBE_SLOT,
  isCompareTurn,
  isLabTurn,
  isTempStudioTurn,
  isTurn,
} from "../types";
import { compareTemplateLabel, CompareTurnView } from "./CompareTurnView";
import { Composer, type OutgoingMessage } from "./Composer";
import { DebugFloat } from "./DebugFloat";
import { emptyLabSlots, LabTurnView } from "./LabTurnView";
import { LabResultsFloat, type LabResultsPayload } from "./LabResultsFloat";
import { FeedbackStatsPanel } from "./FeedbackStatsPanel";
import { ModelsFloat } from "./ModelsFloat";
import { ParetoPanel } from "./ParetoPanel";
import { PerformanceStudioPanel } from "./PerformanceStudioPanel";
import { MediaJobCard } from "./MediaJobCard";
import { emptyTempStudioSlots, TempStudioTurnView } from "./TempStudioTurnView";
import { TurnView } from "./Turn";
import { runTempStudioJudge } from "../strategies/tempJudge";
import {
  TEMP_SLOT_IDS,
  normalizeTempTriple,
  slotDefsFromTemps,
  tempsRecord,
  type TempSlotId,
} from "../strategies/tempStudio";

const SUGGESTIONS = [
  "С чем ты можешь помочь?",
  "Сформулируй это тремя пунктами",
  "Задавай мне по одному вопросу за раз",
];

const TEMP_STUDIO_SUGGESTIONS = [
  "Придумай слоган для приложения утренних привычек",
  "Объясни, что такое HTTP, простыми словами",
  "Напиши короткую басню про лису и API",
];

const STICK_THRESHOLD = 80;

/** Panels sharing the float dock. Only one may be expanded at a time. */
type FloatId = "debug" | "results" | "models";

function toTurn(message: MessageDto): Turn {
  return {
    id: message.id,
    role: message.role === "assistant" ? "assistant" : "user",
    content: message.content,
    modelId: message.model_id,
    messageId: message.id,
    feedback: message.feedback ?? null,
    cascadeStage: message.cascade_stage ?? "off",
  };
}

export function Chat({
  session,
  onStaleSession,
  onFirstMessage,
}: {
  session: SessionCredentials;
  onStaleSession: () => void;
  onFirstMessage?: (text: string) => void;
}) {
  const [items, setItems] = useState<ThreadItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [seed, setSeed] = useState<{ text: string; nonce: number } | null>(null);
  const [status, setStatus] = useState("");
  const [activeFloat, setActiveFloat] = useState<FloatId | null>(null);
  const [resultsPayload, setResultsPayload] = useState<LabResultsPayload | null>(null);
  const [labExpanded, setLabExpanded] = useState<Record<string, boolean>>({});
  const [activeMediaJob, setActiveMediaJob] = useState<MediaJobState | null>(null);

  // Float mutex: at most one panel is expanded. A `false` from a panel only
  // closes the dock when that panel is the one currently open, so a stale
  // collapse never steals the slot from whichever panel just claimed it.
  const setFloat = useCallback((id: FloatId, next: boolean) => {
    setActiveFloat((current) => (next ? id : current === id ? null : current));
  }, []);
  const openResults = useCallback(() => setFloat("results", true), [setFloat]);
  const closeResults = useCallback(() => setFloat("results", false), [setFloat]);
  const openDebug = useCallback((next: boolean) => setFloat("debug", next), [setFloat]);
  const openModels = useCallback((next: boolean) => setFloat("models", next), [setFloat]);

  const thread = useRef<HTMLDivElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const abort = useRef<AbortController | null>(null);
  const { push: debug } = useDebugLog();

  const reportStaleSession = useEffectEvent(() => {
    onStaleSession();
  });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listMessages(session)
      .then((history) => {
        if (cancelled) return;
        setItems(history.filter((m) => m.role !== "system").map(toTurn));
      })
      .catch((e: Error) => {
        if (cancelled) return;
        if (isNotFound(e)) {
          reportStaleSession();
          return;
        }
        setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  useEffect(() => {
    if (stick.current) end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [items]);

  useEffect(() => () => abort.current?.abort(), []);

  const onScroll = useCallback(() => {
    const el = thread.current;
    if (!el) return;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_THRESHOLD;
  }, []);

  const patchCompareSide = useCallback(
    (compareId: string, side: "baseline" | "constrained", patch: Partial<typeof EMPTY_PROBE_SLOT>) => {
      setItems((prev) =>
        prev.map((item) => {
          if (!isCompareTurn(item) || item.id !== compareId) return item;
          return { ...item, [side]: { ...item[side], ...patch } };
        }),
      );
    },
    [],
  );

  const patchLabSlot = useCallback(
    (labId: string, strategyId: PromptStrategyId, patch: Partial<typeof EMPTY_PROBE_SLOT>) => {
      setItems((prev) =>
        prev.map((item) => {
          if (!isLabTurn(item) || item.id !== labId) return item;
          return {
            ...item,
            slots: {
              ...item.slots,
              [strategyId]: { ...item.slots[strategyId], ...patch },
            },
          };
        }),
      );
    },
    [],
  );

  const patchLabJudge = useCallback((labId: string, judge: LabTurnJudge) => {
    setItems((prev) =>
      prev.map((item) =>
        isLabTurn(item) && item.id === labId ? { ...item, judge, compact: true } : item,
      ),
    );
  }, []);

  const patchTempSlot = useCallback(
    (studioId: string, slotId: TempSlotId, patch: Partial<typeof EMPTY_PROBE_SLOT>) => {
      setItems((prev) =>
        prev.map((item) => {
          if (!isTempStudioTurn(item) || item.id !== studioId) return item;
          return {
            ...item,
            slots: {
              ...item.slots,
              [slotId]: { ...item.slots[slotId], ...patch },
            },
          };
        }),
      );
    },
    [],
  );

  const patchTempJudge = useCallback(
    (
      studioId: string,
      patch: {
        judge?: TempStudioJudge;
        judgeLoading?: boolean;
      },
    ) => {
      setItems((prev) =>
        prev.map((item) =>
          isTempStudioTurn(item) && item.id === studioId ? { ...item, ...patch } : item,
        ),
      );
    },
    [],
  );

  const sendSingle = useCallback(
    async (
      { display, api, modelId }: OutgoingMessage,
      controller: AbortController,
      hadTurns: boolean,
    ) => {
      const replyId = `reply-${Date.now()}`;
      debug("info", `SSE сообщение · model=${modelId}`);
      setItems((prev) => [
        ...prev,
        { id: `sent-${Date.now()}`, role: "user", content: display, modelId: null },
        { id: replyId, role: "assistant", content: "", modelId: null },
      ]);
      if (!hadTurns) onFirstMessage?.(display);

      const patch = (change: Partial<Turn>) =>
        setItems((prev) =>
          prev.map((item) =>
            isTurn(item) && item.id === replyId ? { ...item, ...change } : item,
          ),
        );

      try {
        await sendMessageSSE(
          session,
          api,
          (event: ChatEvent) => {
            switch (event.type) {
              case "model":
                patch({ modelId: event.model_id });
                debug("model", event.model_id);
                setStatus(`Отвечает ${event.model_id}.`);
                break;
              case "tool_start": {
                const kind = event.name === "generate_video" ? "video" : "image";
                const job = {
                  kind: kind as "image" | "video",
                  phase: "running" as const,
                  startedAt: Date.now(),
                };
                patch({ mediaJob: job });
                setActiveMediaJob(job);
                setStatus(
                  kind === "video" ? "Генерирую видео…" : "Генерирую картинку…",
                );
                debug("info", `media job start · ${kind}`);
                break;
              }
              case "tool_result":
                if (event.status === "error") {
                  debug("error", event.error || "media tool error");
                  const errJob = {
                    kind:
                      event.name === "generate_video"
                        ? ("video" as const)
                        : ("image" as const),
                    phase: "error" as const,
                    startedAt: Date.now(),
                    error: event.error || "Медиа-инструмент не сработал.",
                  };
                  patch({ mediaJob: errJob });
                  setActiveMediaJob(errJob);
                  setStatus(event.error || "Медиа-инструмент не сработал.");
                } else {
                  patch({
                    mediaJob: {
                      kind:
                        event.name === "generate_video"
                          ? ("video" as const)
                          : ("image" as const),
                      phase: "done",
                      startedAt: Date.now(),
                      providerLabel: event.provider_label,
                    },
                  });
                  setActiveMediaJob(null);
                  setStatus(
                    event.provider_label
                      ? `Готово: ${event.provider_label}`
                      : "Медиа готово.",
                  );
                }
                break;
              case "token":
                setItems((prev) =>
                  prev.map((item) =>
                    isTurn(item) && item.id === replyId
                      ? {
                          ...item,
                          content: item.content + event.text,
                          // Hide running card once media markdown arrives
                          mediaJob:
                            item.mediaJob?.phase === "running" && event.text.trim()
                              ? { ...item.mediaJob, phase: "done" }
                              : item.mediaJob,
                        }
                      : item,
                  ),
                );
                break;
              case "message_end":
                patch({
                  content: event.content,
                  modelId: event.model_id,
                  mediaJob: null,
                  // First moment the live turn has a real server id (prep D10):
                  // the feedback strip appears only from here on.
                  messageId: event.message_id,
                  // Same frame, same reason: the stage is knowable only once
                  // the answer is whole. Absent (the probe stream) means «off».
                  cascadeStage: event.cascade_stage ?? "off",
                });
                setActiveMediaJob(null);
                debug("info", `SSE готово · ${event.model_id}`);
                setStatus(`Ответ готов, модель ${event.model_id}.`);
                break;
              case "error":
                patch({ failed: true });
                setActiveMediaJob(null);
                debug("error", event.message);
                setError(event.message);
                setStatus("Ответ прерван.");
                break;
            }
          },
          controller.signal,
          { model: modelId },
        );
      } catch (e) {
        if (controller.signal.aborted) {
          patch({ failed: true });
        }
        throw e;
      }
    },
    [session, onFirstMessage, debug],
  );

  const sendCompare = useCallback(
    async (
      { display, api, effective }: OutgoingMessage,
      controller: AbortController,
      hadTurns: boolean,
    ) => {
      const compareId = `compare-${Date.now()}`;
      debug("lab", "Compare ×2 start");
      setItems((prev) => [
        ...prev,
        { id: `sent-${Date.now()}`, role: "user", content: display, modelId: null },
        {
          kind: "compare",
          id: compareId,
          templateLabel: compareTemplateLabel(effective),
          baseline: { ...EMPTY_PROBE_SLOT },
          constrained: { ...EMPTY_PROBE_SLOT },
        },
      ]);
      if (!hadTurns) onFirstMessage?.(display);
      setStatus("Сравниваем два ответа (до ~4 мин)…");

      const runSide = async (
        side: "baseline" | "constrained",
        prompt: string,
        body: { model: string } & Record<string, unknown>,
      ) => {
        try {
          const result = await probeComplete(
            prompt,
            body as Parameters<typeof probeComplete>[1],
            controller.signal,
          );
          debug("model", `×2 ${side}: ${result.model_id}`);
          patchCompareSide(compareId, side, {
            loading: false,
            error: null,
            content: result.content,
            modelId: result.model_id,
          });
        } catch (e) {
          if (controller.signal.aborted) {
            patchCompareSide(compareId, side, {
              loading: false,
              error: null,
              content: "",
              modelId: null,
              aborted: true,
            });
            return;
          }
          const msg = e instanceof Error ? e.message : String(e);
          const timedOut =
            (e instanceof DOMException && e.name === "TimeoutError") ||
            /timeout/i.test(msg);
          debug("error", `×2 ${side}: ${msg}`);
          patchCompareSide(compareId, side, {
            loading: false,
            error: timedOut
              ? "Таймаут ожидания модели — попробуйте ещё раз."
              : msg,
            content: "",
            modelId: null,
          });
        }
      };

      await Promise.all([
        runSide("baseline", display, {
          model: effective.modelId,
          temperature: effective.temperature,
          reasoning: effective.reasoning,
        }),
        runSide("constrained", api, prefsToProbeBody(effective)),
      ]);
      setStatus("Сравнение готово (частичные ошибки остаются в панелях).");
    },
    [patchCompareSide, onFirstMessage, debug],
  );

  const sendTempStudio = useCallback(
    async (
      { display, effective, tempStudioTemps }: OutgoingMessage,
      controller: AbortController,
      hadTurns: boolean,
    ) => {
      const temps = normalizeTempTriple(tempStudioTemps);
      const defs = slotDefsFromTemps(temps);
      const studioId = `temp-${Date.now()}`;
      debug("lab", `Temp studio ×T start t=${temps.join("/")}`);
      setItems((prev) => [
        ...prev,
        { id: `sent-${Date.now()}`, role: "user", content: display, modelId: null },
        {
          kind: "temp_studio",
          id: studioId,
          taskDisplay: display,
          temps: tempsRecord(temps),
          slots: emptyTempStudioSlots(temps),
          judge: null,
          judgeLoading: false,
        },
      ]);
      if (!hadTurns) onFirstMessage?.(display);
      setStatus(`Студия температуры: t=${temps.join(" · ")} (до ~4 мин)…`);

      const collected: Partial<
        Record<TempSlotId, { content: string; modelId: string | null; temperature: number }>
      > = {};

      await Promise.all(
        defs.map(async (def) => {
          const t0 = performance.now();
          try {
            const result = await probeComplete(
              display,
              {
                model: effective.modelId,
                temperature: def.temperature,
                // DeepSeek thinking ignores temperature — force it off for ×T.
                reasoning: false,
                prompt_format: false,
                prompt_length: false,
                prompt_stop: false,
              },
              controller.signal,
            );
            debug("model", `×T ${def.label}: ${result.model_id}`);
            collected[def.id] = {
              content: result.content,
              modelId: result.model_id,
              temperature: def.temperature,
            };
            patchTempSlot(studioId, def.id, {
              loading: false,
              error: null,
              content: result.content,
              modelId: result.model_id,
              latencyMs: Math.round(performance.now() - t0),
            });
          } catch (e) {
            if (controller.signal.aborted) {
              patchTempSlot(studioId, def.id, {
                loading: false,
                error: null,
                content: "",
                modelId: null,
                aborted: true,
              });
              return;
            }
            const msg = e instanceof Error ? e.message : String(e);
            const timedOut =
              (e instanceof DOMException && e.name === "TimeoutError") ||
              /timeout/i.test(msg);
            debug("error", `×T ${def.label}: ${msg}`);
            patchTempSlot(studioId, def.id, {
              loading: false,
              error: timedOut
                ? "Таймаут ожидания модели — попробуйте ещё раз."
                : msg,
              content: "",
              modelId: null,
              latencyMs: Math.round(performance.now() - t0),
            });
          }
        }),
      );

      if (controller.signal.aborted) {
        setStatus("Остановлено.");
        return;
      }

      const answers = TEMP_SLOT_IDS.filter((id) => (collected[id]?.content ?? "").trim()).map(
        (id) => ({
          id,
          content: collected[id]!.content,
          temperature: collected[id]!.temperature,
        }),
      );

      if (answers.length < 2) {
        setStatus("Студия температуры: мало ответов для автооценки.");
        return;
      }

      patchTempJudge(studioId, { judgeLoading: true });
      setStatus("Студия температуры: автооценка…");
      const judge = await runTempStudioJudge({
        task: display,
        answers,
        model: effective.modelId,
        signal: controller.signal,
      });
      if (controller.signal.aborted) {
        patchTempJudge(studioId, { judgeLoading: false });
        setStatus("Остановлено.");
        return;
      }
      patchTempJudge(studioId, { judge, judgeLoading: false });
      setStatus(
        judge.error && !judge.heuristic
          ? "Студия готова; автооценка с ошибкой."
          : "Студия температуры готова — смотрите выводы.",
      );
    },
    [patchTempSlot, patchTempJudge, onFirstMessage, debug],
  );

  const sendLab = useCallback(
    async (
      { display, effective, labMeta }: OutgoingMessage,
      controller: AbortController,
      hadTurns: boolean,
    ) => {
      const labId = `lab-${Date.now()}`;
      const golden = labMeta?.goldenAnswer ?? "";
      const rubric = labMeta?.rubric ?? "";
      debug("lab", `Lab ×4 start · task «${display.slice(0, 48)}…»`);
      setLabExpanded((m) => ({ ...m, [labId]: true }));
      setItems((prev) => [
        ...prev,
        { id: `sent-${Date.now()}`, role: "user", content: display, modelId: null },
        {
          kind: "lab",
          id: labId,
          taskDisplay: display,
          slots: emptyLabSlots(),
          goldenAnswer: golden,
          compact: false,
        },
      ]);
      if (!hadTurns) onFirstMessage?.(display);
      setStatus("Лаборатория: 4 стратегии (долгие запросы до ~4 мин)…");

      const probeOpts = {
        model: effective.modelId,
        temperature: effective.temperature,
        reasoning: effective.reasoning,
        sessionContext: effective.sessionContext,
      };

      const collected: Partial<
        Record<PromptStrategyId, { content: string; modelId: string | null; latencyMs?: number; error: string | null }>
      > = {};

      await Promise.all(
        PROMPT_STRATEGY_IDS.map(async (strategyId) => {
          try {
            debug("lab", `${strategyId}: старт`);
            const result = await runPromptStrategy(
              strategyId,
              display,
              probeOpts,
              controller.signal,
              (hint) => {
                patchLabSlot(labId, strategyId, { statusHint: hint });
                debug("lab", `${strategyId}: ${hint}`);
              },
              (expertSlots) => {
                patchLabSlot(labId, strategyId, { expertSlots, loading: true });
              },
            );
            debug("model", `${strategyId} → ${result.model_id} (${result.latencyMs ?? "?"}мс)`);
            collected[strategyId] = {
              content: result.content,
              modelId: result.model_id,
              latencyMs: result.latencyMs,
              error: null,
            };
            patchLabSlot(labId, strategyId, {
              loading: false,
              error: null,
              content: result.content,
              modelId: result.model_id,
              statusHint: null,
              metaPrompt: result.metaPrompt ?? null,
              expertSlots: result.expertSlots,
              latencyMs: result.latencyMs,
            });
          } catch (e) {
            if (controller.signal.aborted) {
              patchLabSlot(labId, strategyId, {
                loading: false,
                aborted: true,
                statusHint: null,
              });
              collected[strategyId] = { content: "", modelId: null, error: null };
              return;
            }
            const msg = e instanceof Error ? e.message : String(e);
            const timedOut =
              (e instanceof DOMException && e.name === "TimeoutError") ||
              /timeout/i.test(msg);
            const errMsg = timedOut
              ? "Таймаут ожидания модели — слот пропущен."
              : msg;
            debug("error", `${strategyId}: ${errMsg}`);
            collected[strategyId] = { content: "", modelId: null, error: errMsg };
            patchLabSlot(labId, strategyId, {
              loading: false,
              error: errMsg,
              content: "",
              modelId: null,
              statusHint: null,
            });
          }
        }),
      );

      const failed = PROMPT_STRATEGY_IDS.filter((id) => collected[id]?.error).length;
      const ok = PROMPT_STRATEGY_IDS.length - failed;
      setStatus(
        failed
          ? `Судья оценивает ответы (${ok}/4 ок, ${failed} с ошибкой)…`
          : "Судья оценивает ответы…",
      );
      debug("judge", "запуск модели-судьи");

      const answers = PROMPT_STRATEGY_IDS.map((id) => ({
        id,
        content: collected[id]?.content ?? "",
      }));

      const judge = await runLabJudge({
        task: display,
        goldenAnswer: golden,
        rubric,
        answers,
        model: effective.modelId,
        temperature: 0.2,
        signal: controller.signal,
      });
      if (judge.error) debug("error", `судья: ${judge.error}`);
      else debug("judge", `победитель=${judge.winnerId} · ${judge.rationale.slice(0, 80)}`);

      patchLabJudge(labId, judge);

      const payload: LabResultsPayload = {
        labId,
        task: display,
        judge,
        rows: PROMPT_STRATEGY_IDS.map((id) => ({
          id,
          modelId: collected[id]?.modelId ?? null,
          words: countWords(collected[id]?.content ?? ""),
          latencyMs: collected[id]?.latencyMs,
          error: collected[id]?.error ?? null,
        })),
      };
      setResultsPayload(payload);
      setActiveFloat("results");
      setStatus(
        failed
          ? `Лаборатория готова с частичными ошибками (${ok}/4). Смотрите «Результаты».`
          : "Лаборатория готова — смотрите «Результаты».",
      );
    },
    [patchLabSlot, patchLabJudge, onFirstMessage, debug],
  );

  const send = useCallback(
    async (message: OutgoingMessage) => {
      const controller = new AbortController();
      abort.current = controller;

      setSeed(null);
      setError(null);
      setStatus("Ждём ответ.");
      setBusy(true);
      stick.current = true;
      const hadTurns = items.length > 0;

      try {
        if (message.chatMode === "lab") {
          await sendLab(message, controller, hadTurns);
        } else if (message.chatMode === "temp_studio") {
          await sendTempStudio(message, controller, hadTurns);
        } else if (message.chatMode === "compare") {
          await sendCompare(message, controller, hadTurns);
        } else {
          await sendSingle(message, controller, hadTurns);
        }
      } catch (e) {
        if (controller.signal.aborted) {
          setStatus("Остановлено.");
        } else if (isNotFound(e)) {
          onStaleSession();
        } else {
          const msg = e instanceof Error ? e.message : String(e);
          debug("error", msg);
          setError(msg);
        }
      } finally {
        abort.current = null;
        setBusy(false);
        setActiveMediaJob(null);
      }
    },
    [items.length, onStaleSession, sendCompare, sendLab, sendTempStudio, sendSingle, debug],
  );

  const empty = !loading && items.length === 0;

  const latestLabId = useMemo(() => {
    for (let i = items.length - 1; i >= 0; i -= 1) {
      const it = items[i];
      if (isLabTurn(it)) return it.id;
    }
    return null;
  }, [items]);

  return (
    <>
      <div className="thread" ref={thread} onScroll={onScroll}>
        <div className="thread-inner">
          {loading && (
            <p className="center-state">
              <span className="spinner" aria-hidden="true" /> Загружаем переписку…
            </p>
          )}

          {empty && (
            <div className="empty">
              <h2>О чём поговорим?</h2>
              <p>
                Режим <strong>Один</strong> — чат. <strong>×2</strong> — шаблоны.{" "}
                <strong>×T</strong> — температуры 0 / 0.7 / 1.2 с автооценкой.{" "}
                <strong>×4</strong> — лаборатория стратегий. Отладка — плавающая кнопка Debug.
              </p>
              <div className="suggestions">
                {SUGGESTIONS.map((text) => (
                  <button
                    key={text}
                    type="button"
                    className="chip"
                    onClick={() => setSeed({ text, nonce: Date.now() })}
                  >
                    {text}
                  </button>
                ))}
              </div>
              <p className="empty-lab-lead">Для студии температуры (×T)</p>
              <div className="suggestions suggestions-lab">
                {TEMP_STUDIO_SUGGESTIONS.map((text) => (
                  <button
                    key={text}
                    type="button"
                    className="chip chip-lab"
                    onClick={() => setSeed({ text, nonce: Date.now() })}
                  >
                    {text}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            {items.map((item, index) => {
              if (isLabTurn(item)) {
                const expanded = labExpanded[item.id] ?? true;
                return (
                  <LabTurnView
                    key={item.id}
                    turn={item}
                    expanded={expanded}
                    onToggleExpand={() =>
                      setLabExpanded((m) => ({ ...m, [item.id]: !expanded }))
                    }
                    onOpenResults={() => {
                      if (resultsPayload?.labId !== item.id) {
                        setResultsPayload({
                          labId: item.id,
                          task: item.taskDisplay,
                          judge: item.judge ?? null,
                          rows: PROMPT_STRATEGY_IDS.map((id) => ({
                            id,
                            modelId: item.slots[id].modelId,
                            words: countWords(item.slots[id].content),
                            latencyMs: item.slots[id].latencyMs,
                            error: item.slots[id].error,
                          })),
                        });
                      }
                      openResults();
                    }}
                  />
                );
              }
              if (isCompareTurn(item)) {
                return <CompareTurnView key={item.id} turn={item} />;
              }
              if (isTempStudioTurn(item)) {
                return <TempStudioTurnView key={item.id} turn={item} />;
              }
              const streaming =
                busy && index === items.length - 1 && item.role === "assistant";
              return (
                <TurnView
                  key={item.id}
                  turn={item}
                  streaming={streaming}
                  session={session}
                />
              );
            })}
          </div>

          <p className="sr-only" role="status" aria-live="polite">
            {status}
          </p>

          <div ref={end} />
        </div>
      </div>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      {activeMediaJob?.phase === "running" && (
        <div className="media-job-dock">
          <MediaJobCard job={activeMediaJob} compact />
        </div>
      )}

      <Composer
        sessionId={session.id}
        onSend={(message) => void send(message)}
        onStop={() => abort.current?.abort()}
        busy={busy}
        maxChars={MAX_MESSAGE_CHARS}
        seed={seed}
      />

      <div className="float-dock">
        {/* Results above Debug; mutex via `setFloat` — only one panel expands. */}
        <LabResultsFloat
          open={activeFloat === "results"}
          payload={resultsPayload}
          onClose={closeResults}
          onExpand={openResults}
          onJumpToLab={
            latestLabId
              ? () => {
                  document.getElementById(`lab-${latestLabId}`)?.scrollIntoView({
                    behavior: "smooth",
                    block: "start",
                  });
                }
              : undefined
          }
        />
        <DebugFloat open={activeFloat === "debug"} onOpenChange={openDebug} />
        <ModelsFloat
          open={activeFloat === "models"}
          onOpenChange={openModels}
          /* Function form: the panel refetches when the window changes and
             stays idle while the tab is hidden. Lab API failures stay inside
             the panel and never reach the chat thread. */
          studio={({ active }) => <PerformanceStudioPanel active={active} />}
          ranking={({ hours, active }) => <ParetoPanel hours={hours} active={active} />}
          feedback={({ hours, active }) => (
            <FeedbackStatsPanel hours={hours} active={active} />
          )}
        />
      </div>
    </>
  );
}

type LabTurnJudge = NonNullable<import("../types").LabTurn["judge"]>;
type TempStudioJudge = NonNullable<import("../types").TempStudioTurn["judge"]>;

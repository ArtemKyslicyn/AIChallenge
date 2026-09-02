import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";

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
import {
  prefsToProbeBody,
  templateLabelForCompare,
} from "../generationPrefs";
import type { CompareSlotState, ThreadItem, Turn } from "../types";
import { EMPTY_COMPARE_SLOT, isCompareTurn, isTurn } from "../types";
import { CompareTurnView } from "./CompareTurnView";
import { Composer, type OutgoingMessage } from "./Composer";
import { TurnView } from "./Turn";

const SUGGESTIONS = [
  "С чем ты можешь помочь?",
  "Сформулируй это тремя пунктами",
  "Задавай мне по одному вопросу за раз",
];

/** Distance from the bottom, in px, within which the view keeps auto-scrolling. */
const STICK_THRESHOLD = 80;

function toTurn(message: MessageDto): Turn {
  return {
    id: message.id,
    role: message.role === "assistant" ? "assistant" : "user",
    content: message.content,
    modelId: message.model_id,
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

  const thread = useRef<HTMLDivElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const abort = useRef<AbortController | null>(null);

  // Keep latest stale handler without reloading history on every App re-render
  // (refreshHistory after first message used to wipe in-thread compare turns).
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
    (compareId: string, side: "baseline" | "constrained", patch: Partial<CompareSlotState>) => {
      setItems((prev) =>
        prev.map((item) => {
          if (!isCompareTurn(item) || item.id !== compareId) return item;
          return { ...item, [side]: { ...item[side], ...patch } };
        }),
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
                setStatus(`Отвечает ${event.model_id}.`);
                break;
              case "tool_start":
                setStatus(
                  event.name === "generate_video"
                    ? "Генерирую видео…"
                    : "Генерирую картинку…",
                );
                break;
              case "tool_result":
                if (event.status === "error") {
                  setStatus(event.error || "Медиа-инструмент не сработал.");
                } else {
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
                      ? { ...item, content: item.content + event.text }
                      : item,
                  ),
                );
                break;
              case "message_end":
                patch({ content: event.content, modelId: event.model_id });
                setStatus(`Ответ готов, модель ${event.model_id}.`);
                break;
              case "error":
                patch({ failed: true });
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
    [session, onFirstMessage],
  );

  const sendCompare = useCallback(
    async (
      { display, api, modelId, prefs }: OutgoingMessage,
      controller: AbortController,
      hadTurns: boolean,
    ) => {
      const compareId = `compare-${Date.now()}`;
      setItems((prev) => [
        ...prev,
        { id: `sent-${Date.now()}`, role: "user", content: display, modelId: null },
        {
          kind: "compare",
          id: compareId,
          templateLabel: templateLabelForCompare(prefs),
          baseline: { ...EMPTY_COMPARE_SLOT },
          constrained: { ...EMPTY_COMPARE_SLOT },
        },
      ]);
      if (!hadTurns) onFirstMessage?.(display);
      setStatus("Сравниваем два ответа…");

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
          patchCompareSide(compareId, side, {
            loading: false,
            error: e instanceof Error ? e.message : String(e),
            content: "",
            modelId: null,
          });
        }
      };

      await Promise.all([
        runSide(
          "baseline",
          display,
          {
            model: modelId,
            temperature: prefs.temperature,
            reasoning: prefs.reasoning,
          },
        ),
        runSide("constrained", api, prefsToProbeBody(prefs)),
      ]);
      setStatus("Сравнение готово.");
    },
    [patchCompareSide, onFirstMessage],
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
        if (message.compareMode) {
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
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        abort.current = null;
        setBusy(false);
      }
    },
    [items.length, onStaleSession, sendCompare, sendSingle],
  );

  const empty = !loading && items.length === 0;

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
                Выберите модель и режим «Один» или «Два рядом». Шаблон ответа — в настройках. У
                каждого ответа видно, какая модель его дала.
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
            </div>
          )}

          <div>
            {items.map((item, index) => {
              if (isCompareTurn(item)) {
                return (
                  <CompareTurnView key={item.id} turn={item} />
                );
              }
              const streaming =
                busy && index === items.length - 1 && item.role === "assistant";
              return <TurnView key={item.id} turn={item} streaming={streaming} />;
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

      <Composer
        onSend={(message) => void send(message)}
        onStop={() => abort.current?.abort()}
        busy={busy}
        maxChars={MAX_MESSAGE_CHARS}
        seed={seed}
      />
    </>
  );
}

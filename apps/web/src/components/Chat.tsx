import { useCallback, useEffect, useRef, useState } from "react";

import {
  MAX_MESSAGE_CHARS,
  isNotFound,
  listMessages,
  sendMessageSSE,
  type ChatEvent,
  type MessageDto,
  type SessionCredentials,
} from "../api/client";
import type { Turn } from "../types";
import { Composer } from "./Composer";
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
}: {
  session: SessionCredentials;
  onStaleSession: () => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [seed, setSeed] = useState<{ text: string; nonce: number } | null>(null);
  const [status, setStatus] = useState("");

  const thread = useRef<HTMLDivElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    listMessages(session)
      .then((history) => setTurns(history.filter((m) => m.role !== "system").map(toTurn)))
      .catch((e: Error) => {
        if (isNotFound(e)) {
          onStaleSession();
          return;
        }
        setError(e.message);
      })
      .finally(() => setLoading(false));
  }, [session, onStaleSession]);

  useEffect(() => {
    // Only follow the stream while the reader is already at the bottom, so
    // scrolling back to re-read is not yanked away mid-answer.
    if (stick.current) end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns]);

  useEffect(() => () => abort.current?.abort(), []);

  const onScroll = useCallback(() => {
    const el = thread.current;
    if (!el) return;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_THRESHOLD;
  }, []);

  const send = useCallback(
    async (content: string) => {
      const replyId = `reply-${Date.now()}`;
      const controller = new AbortController();
      abort.current = controller;

      setSeed(null);
      setError(null);
      setStatus("Ждём ответ.");
      setBusy(true);
      stick.current = true;
      setTurns((prev) => [
        ...prev,
        { id: `sent-${Date.now()}`, role: "user", content, modelId: null },
        { id: replyId, role: "assistant", content: "", modelId: null },
      ]);

      const patch = (change: Partial<Turn>) =>
        setTurns((prev) => prev.map((t) => (t.id === replyId ? { ...t, ...change } : t)));

      try {
        await sendMessageSSE(
          session,
          content,
          (event: ChatEvent) => {
            switch (event.type) {
              case "model":
                // Arrives before the first token, so the label never lags.
                patch({ modelId: event.model_id });
                setStatus(`Отвечает ${event.model_id}.`);
                break;
              case "token":
                setTurns((prev) =>
                  prev.map((t) =>
                    t.id === replyId ? { ...t, content: t.content + event.text } : t,
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
        );
      } catch (e) {
        if (controller.signal.aborted) {
          // Stopping is a choice, not a failure. The server persists whatever
          // arrived, so the reply stays readable and is marked interrupted.
          patch({ failed: true });
        } else if (isNotFound(e)) {
          onStaleSession();
        } else {
          patch({ failed: true });
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        abort.current = null;
        setBusy(false);
      }
    },
    [session, onStaleSession],
  );

  const empty = !loading && turns.length === 0;

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
                У каждого ответа видно, какая модель его дала. Текст приходит потоком, токен
                за токеном.
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
            {turns.map((turn, index) => (
              <TurnView
                key={turn.id}
                turn={turn}
                streaming={busy && index === turns.length - 1 && turn.role === "assistant"}
              />
            ))}
          </div>

          {/* One short status line instead of a live region over the whole
              thread, which would re-announce every token. */}
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
        onSend={(text) => void send(text)}
        onStop={() => abort.current?.abort()}
        busy={busy}
        maxChars={MAX_MESSAGE_CHARS}
        seed={seed}
      />
    </>
  );
}

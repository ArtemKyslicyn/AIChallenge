import { useEffect, useState } from "react";

import type { SessionCredentials } from "../api/client";
import { extractComicFromContent, stripComicFence } from "../comic";
import type { Turn } from "../types";
import { ComicStrip } from "./ComicStrip";
import { FeedbackStrip } from "./FeedbackStrip";
import { Markdown } from "./Markdown";
import { MediaJobCard } from "./MediaJobCard";

/**
 * Checklist keys `escalated_badge` / `escalated_hint`
 * (`docs/superpowers/specs/2026-09-03-lab-observability-ux-checklist.md`).
 */
function shortModelBadge(modelId: string): string {
  if (modelId.startsWith("ollama/")) return modelId.slice("ollama/".length);
  const tail = modelId.includes("/") ? modelId.split("/").pop() || modelId : modelId;
  return tail.length > 28 ? `${tail.slice(0, 26)}…` : tail;
}

function LocalLoadHint({ modelId }: { modelId: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const id = window.setInterval(() => {
      setSeconds(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => window.clearInterval(id);
  }, []);
  const local = modelId.startsWith("ollama/");
  return (
    <p className="body turn-load-hint" role="status">
      <code title={modelId}>{shortModelBadge(modelId)}</code>
      {local ? " · с компа" : null} · {seconds} с · Модель грузится, до 90 с.
    </p>
  );
}

const ESCALATED_BADGE = "эскалировали";
const ESCALATED_HINT = "Дешёвая модель не справилась — ответила модель посильнее";

interface Props {
  turn: Turn;
  streaming: boolean;
  /** Owner session — required to vote; without it the strip stays hidden. */
  session?: SessionCredentials;
}

export function TurnView({ turn, streaming, session }: Props) {
  const isAssistant = turn.role === "assistant";
  const comic = turn.comic ?? (isAssistant ? extractComicFromContent(turn.content) : null);
  const bodyText = isAssistant ? stripComicFence(turn.content) : turn.content;
  const showMediaJob =
    isAssistant &&
    turn.mediaJob &&
    (turn.mediaJob.phase === "running" || turn.mediaJob.phase === "error") &&
    turn.mediaJob.kind !== "comic";
  const emptyBody = isAssistant && !bodyText.trim() && !comic;
  const localWait =
    emptyBody && streaming && Boolean(turn.modelId?.startsWith("ollama/"));
  // Prep D10: a live reply has no server id until `message_end`, so this is
  // also the «no feedback mid-stream» guard the checklist (H5) asks for.
  // A cut-off or empty answer is not rateable either: an abort that lands after
  // `message_end` would otherwise show «прервано» next to a live rating strip.
  const feedbackId =
    isAssistant && !streaming && session && !turn.failed && !emptyBody ? turn.messageId : null;

  return (
    <article
      className={`turn ${turn.role}${turn.failed ? " failed" : ""}${
        streaming ? " streaming" : ""
      }`}
      aria-label={isAssistant ? "Ответ ассистента" : "Ваше сообщение"}
    >
      {showMediaJob && turn.mediaJob && <MediaJobCard job={turn.mediaJob} />}

      {isAssistant ? (
        // The caret is attached in CSS to the last rendered block, so it keeps
        // flowing with the text while Markdown re-renders on every token.
        emptyBody && showMediaJob ? null : localWait && turn.modelId ? (
          <LocalLoadHint modelId={turn.modelId} />
        ) : (
          <div className="body">
            {bodyText.trim() ? <Markdown streaming={streaming}>{bodyText}</Markdown> : null}
            {comic ? <ComicStrip comic={comic} /> : null}
          </div>
        )
      ) : (
        // What the reader typed is shown verbatim, never re-interpreted.
        <p className="body">{turn.content}</p>
      )}

      {isAssistant && (
        <div className="meta">
          {turn.failed ? (
            <span className="badge" data-tone="error" title={turn.modelId || undefined}>
              прервано{turn.modelId ? ` · ${shortModelBadge(turn.modelId)}` : ""}
            </span>
          ) : turn.modelId ? (
            <span
              className="badge"
              data-local={turn.modelId.startsWith("ollama/") ? "1" : undefined}
              title={turn.modelId}
            >
              {turn.modelId.startsWith("ollama/") ? "с компа · " : ""}
              {shortModelBadge(turn.modelId)}
            </span>
          ) : turn.mediaJob?.phase === "running" ? (
            <span className="badge" data-tone="pending">
              {turn.mediaJob.kind === "video"
                ? "видео…"
                : turn.mediaJob.kind === "comic"
                  ? "комикс…"
                  : "картинка…"}
            </span>
          ) : (
            <span className="badge" data-tone="pending">
              выбираем модель…
            </span>
          )}
          {/* Only on `escalated`. The cheap path deliberately gets nothing:
              the absence of the badge is what «обошлись дешёвой» looks like,
              and a badge on every answer would say nothing at all. */}
          {!turn.failed && turn.cascadeStage === "escalated" && (
            <span className="badge" title={ESCALATED_HINT}>
              {ESCALATED_BADGE}
            </span>
          )}
          {feedbackId && session && (
            <FeedbackStrip
              key={feedbackId}
              session={session}
              messageId={feedbackId}
              initialValue={turn.feedback ?? null}
            />
          )}
        </div>
      )}

      {isAssistant && turn.ragSources && turn.ragSources.length > 0 && (
        <details className="rag-sources">
          <summary>
            Источники базы · {turn.ragSources.length}
            {turn.ragRetrieval?.hits_pre != null
              ? ` (было ${turn.ragRetrieval.hits_pre} → ${turn.ragRetrieval.hits_post ?? turn.ragSources.length})`
              : ""}
            {turn.ragRetrieval?.mode ? ` · ${turn.ragRetrieval.mode}` : ""}
          </summary>
          {turn.ragQueryRewritten && turn.ragQueryRewritten !== "" && (
            <p className="rag-sources-rewrite">
              Запрос после rewrite: {turn.ragQueryRewritten}
            </p>
          )}
          <ul>
            {turn.ragSources.map((s) => (
              <li key={s.chunk_id}>
                <strong>{s.title || s.source}</strong>
                {s.section ? ` · ${s.section}` : ""}
                <span className="rag-sources-meta">
                  {" "}
                  ({s.source} · {s.chunk_id} · {s.score.toFixed(2)})
                </span>
                {s.text ? <pre className="rag-sources-quote">{s.text}</pre> : null}
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

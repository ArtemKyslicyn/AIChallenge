import type { Turn } from "../types";
import { Markdown } from "./Markdown";
import { MediaJobCard } from "./MediaJobCard";

interface Props {
  turn: Turn;
  streaming: boolean;
}

export function TurnView({ turn, streaming }: Props) {
  const isAssistant = turn.role === "assistant";
  const showMediaJob =
    isAssistant && turn.mediaJob && (turn.mediaJob.phase === "running" || turn.mediaJob.phase === "error");
  const emptyBody = isAssistant && !turn.content.trim();

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
        emptyBody && showMediaJob ? null : (
          <div className="body">
            <Markdown streaming={streaming}>{turn.content}</Markdown>
          </div>
        )
      ) : (
        // What the reader typed is shown verbatim, never re-interpreted.
        <p className="body">{turn.content}</p>
      )}

      {isAssistant && (
        <div className="meta">
          {turn.failed ? (
            <span className="badge" data-tone="error">
              прервано{turn.modelId ? ` · ${turn.modelId}` : ""}
            </span>
          ) : turn.modelId ? (
            <span className="badge" title="Модель, которая дала этот ответ">
              {turn.modelId}
            </span>
          ) : turn.mediaJob?.phase === "running" ? (
            <span className="badge" data-tone="pending">
              {turn.mediaJob.kind === "video" ? "видео…" : "картинка…"}
            </span>
          ) : (
            <span className="badge" data-tone="pending">
              выбираем модель…
            </span>
          )}
        </div>
      )}
    </article>
  );
}

import type { Turn } from "../types";
import { Markdown } from "./Markdown";

interface Props {
  turn: Turn;
  streaming: boolean;
}

export function TurnView({ turn, streaming }: Props) {
  const isAssistant = turn.role === "assistant";

  return (
    <article
      className={`turn ${turn.role}${turn.failed ? " failed" : ""}${
        streaming ? " streaming" : ""
      }`}
      aria-label={isAssistant ? "Ответ ассистента" : "Ваше сообщение"}
    >
      {isAssistant ? (
        // The caret is attached in CSS to the last rendered block, so it keeps
        // flowing with the text while Markdown re-renders on every token.
        <div className="body">
          <Markdown>{turn.content}</Markdown>
        </div>
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

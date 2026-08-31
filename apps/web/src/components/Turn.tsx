import type { Turn } from "../types";

interface Props {
  turn: Turn;
  streaming: boolean;
}

export function TurnView({ turn, streaming }: Props) {
  const isAssistant = turn.role === "assistant";

  return (
    <article
      className={`turn ${turn.role}${turn.failed ? " failed" : ""}`}
      aria-label={isAssistant ? "Ответ ассистента" : "Ваше сообщение"}
    >
      <p className="body">
        {turn.content}
        {streaming && <span className="caret" aria-hidden="true" />}
      </p>

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

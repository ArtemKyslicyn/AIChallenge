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
      aria-label={isAssistant ? "Assistant reply" : "Your message"}
    >
      <p className="body">
        {turn.content}
        {streaming && <span className="caret" aria-hidden="true" />}
      </p>

      {isAssistant && (
        <div className="meta">
          {turn.failed ? (
            <span className="badge" data-tone="error">
              interrupted{turn.modelId ? ` · ${turn.modelId}` : ""}
            </span>
          ) : turn.modelId ? (
            <span className="badge" title="The model that produced this reply">
              {turn.modelId}
            </span>
          ) : (
            <span className="badge" data-tone="pending">
              choosing model…
            </span>
          )}
        </div>
      )}
    </article>
  );
}

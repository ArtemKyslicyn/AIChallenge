import { countWords, hasEndMarker, hasNumberedTriplet } from "../generationPrefs";
import type { CompareSlotState, CompareTurn } from "../types";
import { Markdown } from "./Markdown";

interface Props {
  turn: CompareTurn;
}

export function CompareTurnView({ turn }: Props) {
  return (
    <article className="turn compare-turn" aria-label="Сравнение двух ответов">
      <div className="compare-thread-grid">
        <ComparePane title="Без шаблона" slot={turn.baseline} />
        <ComparePane title={turn.templateLabel} slot={turn.constrained} showChecks />
      </div>
    </article>
  );
}

function ComparePane({
  title,
  slot,
  showChecks = false,
}: {
  title: string;
  slot: CompareSlotState;
  showChecks?: boolean;
}) {
  return (
    <section className="compare-pane">
      <header className="compare-pane-head">
        <h3>{title}</h3>
        {slot.modelId && <span className="badge">{slot.modelId}</span>}
      </header>

      {slot.loading && (
        <p className="center-state compare-pane-state">
          <span className="spinner" aria-hidden="true" /> Ждём ответ…
        </p>
      )}

      {!slot.loading && slot.error && <p className="compare-error">{slot.error}</p>}

      {!slot.loading && !slot.error && slot.aborted && (
        <p className="compare-pane-muted">Остановлено</p>
      )}

      {!slot.loading && !slot.error && slot.content && (
        <>
          {showChecks && (
            <p className="compare-meta">
              3 пункта: {hasNumberedTriplet(slot.content) ? "да" : "нет"} · END:{" "}
              {hasEndMarker(slot.content) ? "да" : "нет"} · {countWords(slot.content)} сл.
            </p>
          )}
          <div className="body">
            <Markdown>{slot.content}</Markdown>
          </div>
        </>
      )}
    </section>
  );
}

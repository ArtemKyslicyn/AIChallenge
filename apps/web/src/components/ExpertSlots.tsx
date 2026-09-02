import type { ExpertSlotResult } from "../strategies/runStrategy";
import { Markdown } from "./Markdown";

interface Props {
  slots: ExpertSlotResult[];
}

export function ExpertSlots({ slots }: Props) {
  return (
    <div className="expert-slots" aria-label="Эксперты и итог">
      {slots.map((slot) => (
        <section
          key={slot.id}
          className={[
            "expert-slot",
            slot.loading ? "expert-slot--loading" : "",
            slot.id === "synthesis" ? "expert-slot--synthesis" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          <header className="expert-slot-head">
            <h4 className="expert-slot-title">{slot.label}</h4>
            {slot.loading && <span className="spinner" aria-hidden="true" />}
            {!slot.loading && slot.model_id && (
              <span className="badge">{slot.model_id}</span>
            )}
          </header>
          <div className="expert-slot-body">
            {slot.loading && (
              <p className="center-state compare-pane-state">
                <span className="spinner" aria-hidden="true" /> Пишет…
              </p>
            )}
            {!slot.loading && slot.error && (
              <p className="compare-error">{slot.error}</p>
            )}
            {!slot.loading && !slot.error && !slot.content && (
              <p className="compare-pane-muted">Ожидание…</p>
            )}
            {!slot.loading && !slot.error && slot.content && (
              <div className="body">
                <Markdown>{slot.content}</Markdown>
              </div>
            )}
          </div>
        </section>
      ))}
    </div>
  );
}

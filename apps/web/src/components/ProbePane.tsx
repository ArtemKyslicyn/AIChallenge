import { countWords, hasEndMarker, hasExpertSections, hasNumberedSteps, hasNumberedTriplet } from "../generationPrefs";
import type { ProbeSlotState } from "../types";
import { ExpertSlots } from "./ExpertSlots";
import { Markdown } from "./Markdown";

export function ProbePane({
  title,
  subtitle,
  slot,
  accent,
  showChecks = false,
  checkKind = "template",
  compactBody = false,
}: {
  title: string;
  subtitle?: string;
  slot: ProbeSlotState;
  accent?: "neutral" | "steps" | "meta" | "experts";
  showChecks?: boolean;
  checkKind?: "template" | "strategy";
  /** Show short preview instead of full markdown */
  compactBody?: boolean;
}) {
  const hasExperts = Boolean(slot.expertSlots && slot.expertSlots.length > 0);

  return (
    <section className={`compare-pane${accent ? ` compare-pane--${accent}` : ""}`}>
      <header className="compare-pane-head">
        <div className="compare-pane-titles">
          <h3>{title}</h3>
          {subtitle && <p className="compare-pane-sub">{subtitle}</p>}
        </div>
        {slot.modelId && (
          <span className="badge" title={slot.modelId}>
            {slot.modelId}
          </span>
        )}
      </header>

      {slot.loading && !hasExperts && (
        <p className="center-state compare-pane-state">
          <span className="spinner" aria-hidden="true" />{" "}
          {slot.statusHint ?? "Ждём ответ…"}
        </p>
      )}

      {hasExperts && <ExpertSlots slots={slot.expertSlots!} />}

      {!slot.loading && slot.error && !hasExperts && (
        <p className="compare-error">{slot.error}</p>
      )}

      {!slot.loading && !slot.error && slot.aborted && (
        <p className="compare-pane-muted">Остановлено</p>
      )}

      {!slot.loading && slot.metaPrompt && (
        <details className="lab-meta-preview">
          <summary>Сгенерированный промпт (фаза 1)</summary>
          <pre>{slot.metaPrompt}</pre>
        </details>
      )}

      {!slot.loading && !slot.error && slot.content && !hasExperts && (
        <>
          {showChecks && (
            <p className="compare-meta">
              {checkKind === "template" ? (
                <>
                  3 пункта: {hasNumberedTriplet(slot.content) ? "да" : "нет"} · END:{" "}
                  {hasEndMarker(slot.content) ? "да" : "нет"} · {countWords(slot.content)} сл.
                </>
              ) : (
                <>
                  Шаги: {hasNumberedSteps(slot.content) ? "да" : "нет"} · Эксперты:{" "}
                  {hasExpertSections(slot.content) ? "да" : "нет"} · {countWords(slot.content)} сл.
                  {slot.latencyMs != null ? ` · ${slot.latencyMs} мс` : ""}
                </>
              )}
            </p>
          )}
          {compactBody ? (
            <p className="compare-pane-muted lab-compact-preview">
              {slot.content.trim().slice(0, 160)}
              {slot.content.trim().length > 160 ? "…" : ""}
            </p>
          ) : (
            <div className="body">
              <Markdown>{slot.content}</Markdown>
            </div>
          )}
        </>
      )}
    </section>
  );
}

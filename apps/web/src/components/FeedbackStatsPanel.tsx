import { useEffect, useId, useRef, useState } from "react";

import { getLabFeedbackStats, type LabFeedbackStatsDto } from "../api/client";

/**
 * «Оценки» tab of the Models float: thumbs aggregated per `model_id` from
 * `GET /api/v1/lab/feedback-stats`.
 *
 * Same four states and the same table density as `ParetoPanel` — the two tabs
 * must read as one component family. All copy comes verbatim from
 * `docs/superpowers/specs/2026-09-03-lab-observability-ux-checklist.md`.
 */
const COPY = {
  /** `title_feedback`, not `tab_feedback`: the heading must not repeat the tab. */
  title: "Оценки моделей",
  colModel: "Модель",
  /** `col_down_rate` — the header row is Russian; `down%` was not. */
  colDownRate: "Доля 👎",
  up: "Полезно",
  down: "Не полезно",
  /** `empty_feedback`. Names the mode, not just the buttons: `CompareTurnView`
      and `LabTurnView` render no strip, so «под ответом» alone was a lie for
      anyone who opened this tab from ×2 or ×4. */
  empty:
    "Оценок пока нет. Кнопки «Полезно» / «Не полезно» есть под ответом в режиме «Один» (не в ×2 / ×T / ×4).",
  /** `err_feedback` — this tab no longer borrows the ranking's error. */
  error: "Не удалось загрузить оценки",
  retry: "Повторить",
  sortedBy: "Сортировка: доля 👎 ↓",
  penalized: "Ниже в очереди",
  penalizedHint:
    "Из‑за частых «Не полезно» модель временно реже выбирается автоматически",
} as const;

/** Never render `NaN`: nulls and non-finite numbers become an em dash. */
const DASH = "—";

function num(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatCount(n: number | null | undefined): string {
  const value = num(n);
  return value === null ? DASH : String(value);
}

/** 100% only when the rate really is 1 — see `ParetoPanel.formatPercent`. */
function formatPercent(rate: number | null | undefined): string {
  const value = num(rate);
  if (value === null) return DASH;
  const rounded = Math.round(value * 100);
  return `${rounded === 100 && value < 1 ? 99 : rounded}%`;
}

interface Loaded {
  /** `${hours}:${attempt}` this result belongs to — anything else is stale. */
  key: string;
  data: LabFeedbackStatsDto | null;
  failed: boolean;
}

export interface FeedbackStatsPanelProps {
  /** Observation window; a change refetches while the tab is visible. */
  hours: number;
  /**
   * False while the tab is hidden — the panel stays mounted but never calls
   * the API. Defaults to true so the panel works standalone.
   */
  active?: boolean;
  /** Preloaded payload for mocks/stories: when given, the API is not called. */
  data?: LabFeedbackStatsDto | null;
}

const SKELETON_ROWS = [0, 1, 2];
/** Mirrors the real columns so the skeleton keeps their alignment. */
const SKELETON_CELLS = ["", "feedback-num", "feedback-num", "feedback-num"];

export function FeedbackStatsPanel({ hours, active = true, data }: FeedbackStatsPanelProps) {
  const titleId = useId();
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const wantKey = `${hours}:${attempt}`;
  // Written inside the effect only — keeps `setState` out of the effect body,
  // so a re-render is never triggered synchronously by loading.
  const requested = useRef<string | null>(null);

  useEffect(() => {
    if (data) return;
    if (!active) return;
    if (requested.current === wantKey) return;
    requested.current = wantKey;

    const controller = new AbortController();
    let settled = false;
    getLabFeedbackStats(hours, controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) return;
        settled = true;
        setLoaded({ key: wantKey, data: payload, failed: false });
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        settled = true;
        // A failing Lab API stays inside this panel: chat is untouched.
        setLoaded({ key: wantKey, data: null, failed: true });
      });

    return () => {
      controller.abort();
      // Aborted before it landed (tab hidden / window switched): allow a retry.
      if (!settled) requested.current = null;
    };
  }, [data, active, hours, wantKey]);

  const payload = data ?? (loaded?.key === wantKey && !loaded.failed ? loaded.data : null);
  const failed = !data && loaded?.key === wantKey && loaded.failed;
  const loading = !data && !failed && !payload;

  const retry = () => {
    setAttempt((n) => n + 1);
  };

  const rows = payload?.models ?? [];

  return (
    <section className="feedback-stats" aria-labelledby={titleId}>
      <div className="feedback-stats-head">
        <h3 id={titleId} className="feedback-stats-title">
          {COPY.title}
        </h3>
        <p className="feedback-stats-meta">{COPY.sortedBy}</p>
      </div>

      {failed ? (
        <div className="feedback-stats-error" role="alert">
          <p className="feedback-stats-error-text">{COPY.error}</p>
          <button type="button" className="ghost-button" onClick={retry}>
            {COPY.retry}
          </button>
        </div>
      ) : !loading && rows.length === 0 ? (
        <p className="feedback-stats-empty">{COPY.empty}</p>
      ) : (
        <div className="feedback-stats-table-wrap">
          <table
            className="lab-results-table feedback-stats-table"
            aria-labelledby={titleId}
            aria-busy={loading || undefined}
          >
            <thead>
              <tr>
                <th scope="col">{COPY.colModel}</th>
                {/* Emoji headers keep the tab compact; the accessible name is
                    the same microcopy the strip's buttons use. */}
                <th scope="col" className="feedback-num" title={COPY.up}>
                  <span aria-hidden="true">👍</span>
                  <span className="sr-only">{COPY.up}</span>
                </th>
                <th scope="col" className="feedback-num" title={COPY.down}>
                  <span aria-hidden="true">👎</span>
                  <span className="sr-only">{COPY.down}</span>
                </th>
                <th scope="col" className="feedback-num" aria-sort="descending">
                  {COPY.colDownRate}
                </th>
              </tr>
            </thead>
            <tbody>
              {loading
                ? SKELETON_ROWS.map((row) => (
                    <tr key={`skeleton-${row}`} className="feedback-stats-skeleton-row">
                      {SKELETON_CELLS.map((cell, column) => (
                        <td key={column} className={cell || undefined}>
                          <span className="feedback-stats-skeleton" />
                        </td>
                      ))}
                    </tr>
                  ))
                : rows.map((model) => (
                    <tr key={model.model_id}>
                      <th scope="row" className="feedback-model">
                        <span className="feedback-model-id">{model.model_id}</span>
                        {model.penalized && (
                          // Prep D7: a reorder, never a ban — the tone stays calm.
                          <span className="feedback-chip" title={COPY.penalizedHint}>
                            {COPY.penalized}
                          </span>
                        )}
                      </th>
                      <td className="feedback-num">{formatCount(model.ups)}</td>
                      <td className="feedback-num">{formatCount(model.downs)}</td>
                      <td className="feedback-num">{formatPercent(model.down_rate)}</td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

import { useEffect, useId, useRef, useState } from "react";

import { getLabPareto, type LabParetoDto } from "../api/client";

/**
 * «Рейтинг» tab of the Models float: per-model aggregates from
 * `GET /api/v1/lab/pareto`, already sorted by score desc on the server.
 *
 * All copy comes verbatim from
 * `docs/superpowers/specs/2026-09-03-lab-observability-ux-checklist.md`.
 */
const COPY = {
  title: "Рейтинг моделей",
  colModel: "Модель",
  colN: "N",
  colOk: "Успех",
  colP50: "p50, с",
  colCost: "Cost",
  colScore: "Score",
  hintN: "Сколько раз модель завершила ответ в окне",
  hintOk: "Доля успешных ответов",
  hintP50: "Медиана времени ответа",
  hintCost: "Относительная стоимость (proxy)",
  hintScore: "Успех / время / cost — выше лучше",
  formulaSummary: "Score = успех ÷ время_ответа ÷ cost. Нужен баланс качества, скорости и цены.",
  empty: "Пока нет замеров. Отправьте пару сообщений в чат.",
  error: "Не удалось загрузить рейтинг",
  retry: "Повторить",
  sortedBy: "Сортировка: Score ↓",
  /** Disclosure label — design spec §4 «Progressive disclosure». */
  formulaLabel: "Как считается Score",
} as const;

/** Never render `NaN`: nulls and non-finite numbers become an em dash. */
const DASH = "—";

function num(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** total_ms / 1000, one decimal — «p50, с». */
function formatSeconds(ms: number | null): string {
  const value = num(ms);
  return value === null ? DASH : (value / 1000).toFixed(1);
}

function formatPercent(rate: number | null): string {
  const value = num(rate);
  return value === null ? DASH : `${Math.round(value * 100)}%`;
}

function formatCost(cost: number | null): string {
  const value = num(cost);
  return value === null ? DASH : value.toFixed(2);
}

function formatScore(score: number | null): string {
  const value = num(score);
  if (value === null) return DASH;
  return Math.abs(value) >= 1 ? value.toFixed(2) : value.toFixed(3);
}

function formatCount(n: number | null): string {
  const value = num(n);
  return value === null ? DASH : String(value);
}

interface Loaded {
  /** `${hours}:${attempt}` this result belongs to — anything else is stale. */
  key: string;
  data: LabParetoDto | null;
  failed: boolean;
}

export interface ParetoPanelProps {
  /** Observation window; a change refetches while the tab is visible. */
  hours: number;
  /**
   * False while the tab is hidden — the panel stays mounted but never calls
   * the API. Defaults to true so the panel works standalone.
   */
  active?: boolean;
  /** Preloaded payload for mocks/stories: when given, the API is not called. */
  data?: LabParetoDto | null;
}

const SKELETON_ROWS = [0, 1, 2];
const SKELETON_CELLS = [0, 1, 2, 3, 4, 5];

export function ParetoPanel({ hours, active = true, data }: ParetoPanelProps) {
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
    getLabPareto(hours, controller.signal)
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
    <section className="pareto" aria-labelledby={titleId}>
      <div className="pareto-head">
        <h3 id={titleId} className="pareto-title">
          {COPY.title}
        </h3>
        <p className="pareto-meta">{COPY.sortedBy}</p>
      </div>

      {failed ? (
        <div className="pareto-error" role="alert">
          <p className="pareto-error-text">{COPY.error}</p>
          <button type="button" className="ghost-button" onClick={retry}>
            {COPY.retry}
          </button>
        </div>
      ) : !loading && rows.length === 0 ? (
        <p className="pareto-empty">{COPY.empty}</p>
      ) : (
        <div className="pareto-table-wrap">
          <table
            className="lab-results-table pareto-table"
            aria-labelledby={titleId}
            aria-busy={loading || undefined}
          >
            <thead>
              <tr>
                <th scope="col">{COPY.colModel}</th>
                <th scope="col" className="pareto-num" title={COPY.hintN}>
                  {COPY.colN}
                </th>
                <th scope="col" className="pareto-num" title={COPY.hintOk}>
                  {COPY.colOk}
                </th>
                <th scope="col" className="pareto-num" title={COPY.hintP50}>
                  {COPY.colP50}
                </th>
                <th scope="col" className="pareto-num" title={COPY.hintCost}>
                  {COPY.colCost}
                </th>
                <th scope="col" className="pareto-num" aria-sort="descending" title={COPY.hintScore}>
                  {COPY.colScore}
                </th>
              </tr>
            </thead>
            <tbody>
              {loading
                ? SKELETON_ROWS.map((row) => (
                    <tr key={`skeleton-${row}`} className="pareto-skeleton-row">
                      {SKELETON_CELLS.map((cell) => (
                        <td key={cell}>
                          <span className="pareto-skeleton" />
                        </td>
                      ))}
                    </tr>
                  ))
                : rows.map((model) => (
                    <tr key={model.model_id}>
                      <td className="pareto-model" title={model.model_id}>
                        {model.model_id}
                      </td>
                      <td className="pareto-num">{formatCount(model.n)}</td>
                      <td className="pareto-num">{formatPercent(model.success_rate)}</td>
                      <td className="pareto-num">{formatSeconds(model.p50_total_ms)}</td>
                      <td className="pareto-num">{formatCost(model.avg_cost_proxy)}</td>
                      <td className="pareto-num lab-results-score">{formatScore(model.score)}</td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      )}

      <details className="pareto-formula">
        <summary>{COPY.formulaLabel}</summary>
        <p>{COPY.formulaSummary}</p>
      </details>
    </section>
  );
}

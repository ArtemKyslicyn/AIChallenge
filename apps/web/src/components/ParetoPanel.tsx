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
  colQuality: "Качество",
  colP50: "p50, с",
  colCost: "Cost",
  colScore: "Score",
  hintN: "Сколько раз модель завершила ответ в окне",
  hintOk: "Доля успешных ответов",
  hintNFolded: (n: number) => `Прогонов в окне: ${n}`,
  hintQuality: "Оценка ответов судьёй, 0–100%. В скобках — сколько прогонов оценено",
  hintP50: "Медиана времени ответа",
  hintCost: "Относительная стоимость (proxy)",
  hintScore: "Успех / время / cost — выше лучше",
  formulaSummary:
    "Score = качество (или успех, пока оценок мало) ÷ время_ответа ÷ cost. " +
    "Нужен баланс качества, скорости и цены.",
  empty: "Пока нет замеров. Отправьте пару сообщений в чат.",
  error: "Не удалось загрузить рейтинг",
  retry: "Повторить",
  sortedBy: "Сортировка: Score ↓",
  /** Checklist key `formula_details` — design spec §4 «Progressive disclosure». */
  formulaLabel: "Как считается Score",
} as const;

/** Checklist key `escalation_rate`. One number, one thought, one line. */
function escalationLine(cheap: number, escalated: number): string {
  const total = cheap + escalated;
  return `Эскалации: ${escalated} из ${total} (${formatPercent(total ? escalated / total : 0)})`;
}

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

/**
 * 100% is reserved for a rate that really is 1: `Math.round` alone turned
 * 99.6% into a perfect score, which is the one number a reader would act on.
 */
function formatPercent(rate: number | null): string {
  const value = num(rate);
  if (value === null) return DASH;
  const rounded = Math.round(value * 100);
  return `${rounded === 100 && value < 1 ? 99 : rounded}%`;
}

function formatCost(cost: number | null): string {
  const value = num(cost);
  return value === null ? DASH : value.toFixed(2);
}

/**
 * One precision for the whole column — per-row precision left the decimal
 * points unaligned in the column the table is sorted by. Enough decimals for
 * the smallest score to keep two significant digits, capped at three.
 */
function scorePrecision(scores: (number | null)[]): number {
  const smallest = Math.min(
    ...scores.map((s) => (s === null ? Infinity : Math.abs(s))).filter((s) => s > 0),
  );
  if (!Number.isFinite(smallest) || smallest >= 1) return 2;
  return Math.min(3, Math.max(2, Math.ceil(-Math.log10(smallest)) + 1));
}

function formatScore(score: number | null, precision: number): string {
  const value = num(score);
  return value === null ? DASH : value.toFixed(precision);
}

/**
 * What the cell says on hover: the same percentage plus the sample it came
 * from. The count is the difference between a measurement and an impression,
 * and `hint_quality` promises it in parentheses.
 */
function qualityTitle(quality: number | null, judged: number | null): string | undefined {
  const value = num(quality);
  return value === null ? undefined : `${formatPercent(value)} (${formatCount(judged)})`;
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
/**
 * Mirrors the real columns, so `.pareto-col-n` hides in both (see index.css).
 * «Качество» is not among them: whether that column exists is a fact about the
 * data, and while it is loading there is none to read.
 */
const SKELETON_CELLS = [
  "",
  "pareto-num pareto-col-n",
  "pareto-num",
  "pareto-num",
  "pareto-num",
  "pareto-num",
];

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
  const cascade = payload?.cascade ?? null;
  const precision = scorePrecision(rows.map((model) => num(model.score)));
  // The column exists only when something in the window was actually judged.
  // With no `JUDGE_MODEL` configured nobody judges anything, and a column of
  // dashes would read as a broken feature rather than an unused one — the
  // table has to look exactly as it did before the judge existed.
  const hasQuality = rows.some((model) => num(model.avg_quality) !== null);
  // Narrow screens can hold one rate, not two, and «Качество» is the one that
  // answers the question «Успех» only looks like it answers.
  const okClass = hasQuality ? "pareto-num pareto-col-ok" : "pareto-num";
  // Seven columns do not fit beside a model id in a 360px float. N is the one
  // that is metadata rather than a ranking axis, so it folds into the model
  // cell's title once quality — which is a ranking axis — needs the space.
  const nClass = hasQuality
    ? "pareto-num pareto-col-n pareto-col-n--folded"
    : "pareto-num pareto-col-n";

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
                <th scope="col" className={nClass} title={COPY.hintN}>
                  {COPY.colN}
                </th>
                <th scope="col" className={okClass} title={COPY.hintOk}>
                  {COPY.colOk}
                </th>
                {hasQuality && (
                  <th scope="col" className="pareto-num" title={COPY.hintQuality}>
                    {COPY.colQuality}
                  </th>
                )}
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
                      {SKELETON_CELLS.map((cell, column) => (
                        <td key={column} className={cell || undefined}>
                          <span className="pareto-skeleton" />
                        </td>
                      ))}
                    </tr>
                  ))
                : rows.map((model, index) => (
                    // Server sorts by score desc, so the first row is the pick.
                    // `data-winner` is the Lab results table's own idiom.
                    <tr key={model.model_id} data-winner={index === 0 ? "true" : undefined}>
                      <th
                        scope="row"
                        className="pareto-model"
                        title={hasQuality ? COPY.hintNFolded(model.n) : undefined}
                      >
                        {model.model_id}
                      </th>
                      <td className={nClass}>{formatCount(model.n)}</td>
                      <td className={okClass}>{formatPercent(model.success_rate)}</td>
                      {hasQuality && (
                        <td
                          className="pareto-num"
                          title={qualityTitle(model.avg_quality, model.judged_n)}
                        >
                          {formatPercent(model.avg_quality)}
                        </td>
                      )}
                      <td className="pareto-num">{formatSeconds(model.p50_total_ms)}</td>
                      <td className="pareto-num">{formatCost(model.avg_cost_proxy)}</td>
                      <td className="pareto-num lab-results-score">
                        {formatScore(model.score, precision)}
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Only when the window actually saw the cascade run — a zero would
          claim it ran and escalated nothing, which is a different fact. One
          `.pareto-meta` line under the table, never a section of its own. */}
      {cascade && (
        <p className="pareto-meta">{escalationLine(cascade.cheap, cascade.escalated)}</p>
      )}

      {/* Bottom-anchored float: expanding used to reveal the text below the
          panel's edge, so the click looked like it did nothing. */}
      <details
        className="pareto-formula"
        onToggle={(e) => {
          if (e.currentTarget.open) e.currentTarget.scrollIntoView({ block: "nearest" });
        }}
      >
        <summary>{COPY.formulaLabel}</summary>
        <p>{COPY.formulaSummary}</p>
      </details>
    </section>
  );
}

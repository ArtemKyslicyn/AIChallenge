import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  fetchHarnessLeaderboard,
  refreshHarnessLeaderboard,
  type HarnessLeaderboard,
} from "../api/client";

function formatNum(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("ru-RU");
}

export function BenchmarksBoard() {
  const [data, setData] = useState<HarnessLeaderboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    return fetchHarnessLeaderboard(signal)
      .then((board) => {
        setData(board);
        setError(null);
      })
      .catch((e: unknown) => {
        if (signal?.aborted) return;
        const message =
          e instanceof ApiError ? e.message : "Не удалось загрузить рейтинг.";
        setError(message);
      })
      .finally(() => {
        if (!signal?.aborted) setLoading(false);
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const board = await refreshHarnessLeaderboard();
      setData(board);
    } catch (e: unknown) {
      const message =
        e instanceof ApiError ? e.message : "Не удалось обновить снимок.";
      setError(message);
    } finally {
      setRefreshing(false);
    }
  }, []);

  const ranked = data?.rows.filter((r) => r.matched) ?? [];
  const unmatched = data?.rows.filter((r) => !r.matched) ?? [];
  const fullBoard = data?.board ?? [];
  const coverage = data?.coverage;

  return (
    <div className="bench-board">
      <header className="bench-board-top">
        <div>
          <h2>Benchmarks</h2>
          <p className="bench-board-sub">
            Рейтинг по{" "}
            <a
              href={data?.source_url || "https://github.com/ai-forever/harness-bench-fast"}
              target="_blank"
              rel="noreferrer"
            >
              harness-bench-fast
            </a>
            : Result = passed/total, % = passed/total×100
            {data ? ` · task-set ${data.task_set} · ${data.total_tasks} задач` : null}
            {coverage
              ? ` · в цепочке ${coverage.matched}/${coverage.connected} с измерением`
              : null}
          </p>
        </div>
        <div className="bench-board-actions">
          <button
            type="button"
            className="ghost-button"
            disabled={refreshing || loading}
            onClick={() => void onRefresh()}
          >
            {refreshing ? "Обновляю…" : "Обновить снимок"}
          </button>
          {data?.landing_url ? (
            <a
              className="ghost-button"
              href={data.landing_url}
              target="_blank"
              rel="noreferrer"
            >
              Публичная борда
            </a>
          ) : null}
        </div>
      </header>

      {loading ? <p className="bench-board-muted">Загрузка…</p> : null}
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}

      {!loading && data ? (
        <>
          <section>
            <h3 className="bench-section-title">Наши модели (LLM_MODEL_CHAIN)</h3>
            <div className="bench-table-wrap">
              <table className="bench-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Модель</th>
                    <th>Harness</th>
                    <th>Profile</th>
                    <th>Result</th>
                    <th>%</th>
                    <th>Steps</th>
                    <th>Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {ranked.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="bench-board-muted">
                        Нет совпадений снимка с моделями из цепочки.
                      </td>
                    </tr>
                  ) : (
                    ranked.map((row) => (
                      <tr key={row.model_id}>
                        <td>{row.rank ?? "—"}</td>
                        <td>
                          <div className="bench-model">
                            <strong>{row.model_label}</strong>
                            <code>{row.model_id}</code>
                          </div>
                        </td>
                        <td>{row.harness || "—"}</td>
                        <td>{row.profile || "—"}</td>
                        <td>
                          {row.passed != null && row.total != null
                            ? `${row.passed}/${row.total}`
                            : "—"}
                        </td>
                        <td>{row.pct != null ? `${row.pct}%` : "—"}</td>
                        <td>{formatNum(row.steps)}</td>
                        <td>{formatNum(row.tokens)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {unmatched.length > 0 ? (
            <section className="bench-unmatched">
              <h3>В цепочке, но нет в harness-bench (ещё не измерены)</h3>
              <ul>
                {unmatched.map((row) => (
                  <li key={row.model_id}>
                    <code>{row.model_id}</code>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section>
            <h3 className="bench-section-title">Полная борда harness-bench-fast</h3>
            <div className="bench-table-wrap">
              <table className="bench-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Модель</th>
                    <th>Harness</th>
                    <th>Profile</th>
                    <th>Result</th>
                    <th>%</th>
                    <th>Steps</th>
                    <th>Tokens</th>
                    <th>Цепочка</th>
                  </tr>
                </thead>
                <tbody>
                  {fullBoard.map((row) => (
                    <tr
                      key={`${row.rank}-${row.model_label}-${row.harness}`}
                      className={row.in_chain ? "bench-row--ours" : undefined}
                    >
                      <td>{row.rank}</td>
                      <td>
                        <div className="bench-model">
                          <strong>{row.model_label}</strong>
                          {row.linked_model_ids.length > 0 ? (
                            <code>{row.linked_model_ids.join(", ")}</code>
                          ) : null}
                        </div>
                      </td>
                      <td>{row.harness}</td>
                      <td>{row.profile || "—"}</td>
                      <td>
                        {row.passed}/{row.total}
                      </td>
                      <td>{row.pct}%</td>
                      <td>{formatNum(row.steps)}</td>
                      <td>{formatNum(row.tokens)}</td>
                      <td>{row.in_chain ? "да" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <p className="bench-board-hint">
            Снимок: кнопка «Обновить» или cron/timer{" "}
            <code>harness-board-sync.timer</code>
            {data.updated_at ? ` · updated ${data.updated_at}` : null}.
          </p>
        </>
      ) : null}
    </div>
  );
}

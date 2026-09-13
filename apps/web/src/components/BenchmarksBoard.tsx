import { useEffect, useState } from "react";

import {
  ApiError,
  fetchHarnessLeaderboard,
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

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchHarnessLeaderboard(controller.signal)
      .then((board) => {
        setData(board);
        setError(null);
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          e instanceof ApiError ? e.message : "Не удалось загрузить рейтинг.";
        setError(message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const ranked = data?.rows.filter((r) => r.matched) ?? [];
  const unmatched = data?.rows.filter((r) => !r.matched) ?? [];

  return (
    <div className="bench-board">
      <header className="bench-board-top">
        <div>
          <h2>Benchmarks</h2>
          <p className="bench-board-sub">
            Рейтинг подключённых моделей по{" "}
            <a
              href={data?.source_url || "https://github.com/ai-forever/harness-bench-fast"}
              target="_blank"
              rel="noreferrer"
            >
              harness-bench-fast
            </a>
            : Result = passed/total, % = passed/total×100
            {data ? ` · task-set ${data.task_set} · ${data.total_tasks} задач` : null}
          </p>
        </div>
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
      </header>

      {loading ? <p className="bench-board-muted">Загрузка…</p> : null}
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}

      {!loading && data ? (
        <>
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
                      Нет совпадений снимка бенча с моделями из цепочки.
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

          {unmatched.length > 0 ? (
            <section className="bench-unmatched">
              <h3>В цепочке, но без измерения в снимке</h3>
              <ul>
                {unmatched.map((row) => (
                  <li key={row.model_id}>
                    <code>{row.model_id}</code>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <p className="bench-board-hint">
            Снимок обновляется скриптом <code>scripts/sync-harness-board.py</code>
            {data.updated_at ? ` · updated ${data.updated_at}` : null}.
          </p>
        </>
      ) : null}
    </div>
  );
}

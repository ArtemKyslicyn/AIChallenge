import { FormEvent, useCallback, useEffect, useState } from "react";

import {
  getMcpPulse,
  listMcpTools,
  runAgentWorkshop,
  type AgentMcpCallDto,
  type AgentWorkshopRunResultDto,
  type McpCatalogDto,
  type McpPulseDto,
} from "../api/client";

const PULSE_AGENT = {
  name: "Stand Pulse",
  system_prompt:
    "Ты дежурный оператор стенда. Если нужен статус, рейтинг или сводка — вызывай MCP-инструменты probe_stand, model_pulse, latest_digest, schedule_digest, list_jobs. Отвечай только по фактам из результата инструмента.",
  preferred_model: "auto",
  temperature: 0.2,
  max_tokens: 700,
};

const PRESETS = [
  { id: "probe", label: "Проверить стенд", message: "Проверь здоровье стенда" },
  { id: "rank", label: "Рейтинг моделей", message: "Покажи рейтинг моделей за 24 часа" },
  { id: "digest", label: "Последняя сводка", message: "Дай последнюю сводку" },
  {
    id: "schedule",
    label: "Сводка каждые 60 с",
    message: "Поставь периодическую сводку каждые 60 секунд",
  },
] as const;

function paramSummary(tool: McpCatalogDto["tools"][number]): string {
  const props = tool.parameters?.properties;
  if (!props || Object.keys(props).length === 0) return "—";
  return Object.entries(props)
    .map(([name, spec]) => {
      const type = spec.type ? `:${spec.type}` : "";
      const fallback = spec.default !== undefined ? `=${String(spec.default)}` : "";
      return `${name}${type}${fallback}`;
    })
    .join(", ");
}

export function McpCatalog() {
  const [data, setData] = useState<McpCatalogDto | null>(null);
  const [pulse, setPulse] = useState<McpPulseDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [ask, setAsk] = useState("Проверь здоровье стенда");
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState<AgentWorkshopRunResultDto | null>(null);
  const [askError, setAskError] = useState<string | null>(null);

  const refreshPulse = useCallback((signal?: AbortSignal) => {
    return getMcpPulse(signal)
      .then((next) => setPulse(next))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const ac = new AbortController();
    listMcpTools(ac.signal)
      .then((next) => {
        setData(next);
        setError(null);
      })
      .catch((exc: Error) => {
        if (exc.name === "AbortError") return;
        setError(exc.message);
      })
      .finally(() => setLoading(false));
    void refreshPulse(ac.signal);
    return () => ac.abort();
  }, [refreshPulse]);

  async function runAsk(message: string) {
    const text = message.trim();
    if (!text || busy) return;
    setBusy(true);
    setAskError(null);
    try {
      const result = await runAgentWorkshop(PULSE_AGENT, text);
      setReply(result);
      await refreshPulse();
    } catch (exc) {
      setAskError(exc instanceof Error ? exc.message : "не удалось вызвать агента");
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void runAsk(ask);
  }

  const digest = pulse?.latest_digest;
  const health = digest?.health;
  const ranking = digest?.pulse?.ranking ?? [];

  return (
    <section className="mcp-board mcp-board--pulse" aria-labelledby="mcp-title">
      <header className="mcp-board-top">
        <div>
          <h2 id="mcp-title">MCP</h2>
          <p className="mcp-board-sub">
            Stand Pulse — живые инструменты стенда: health, рейтинг моделей, периодическая сводка.
            Агент вызывает MCP и отвечает по фактам.
          </p>
        </div>
        <p className="mcp-status" data-state={data?.connected ? "ok" : "off"} aria-live="polite">
          {loading
            ? "подключаемся…"
            : data?.connected
              ? `connected · ${data.protocol}${data.server ? ` · ${data.server}` : ""}`
              : `нет соединения${data?.error || error ? ` · ${data?.error || error}` : ""}`}
        </p>
      </header>

      {error && !data ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}

      <table className="mcp-tools">
        <caption>Доступные инструменты</caption>
        <thead>
          <tr>
            <th scope="col">name</th>
            <th scope="col">description</th>
            <th scope="col">params</th>
          </tr>
        </thead>
        <tbody>
          {(data?.tools ?? []).map((tool) => (
            <tr key={tool.name}>
              <td>
                <code>{tool.name}</code>
              </td>
              <td>{tool.description}</td>
              <td>
                <code>{paramSummary(tool)}</code>
              </td>
            </tr>
          ))}
          {!loading && (data?.tools.length ?? 0) === 0 ? (
            <tr>
              <td colSpan={3}>Список пуст — сервер не ответил или токен не задан.</td>
            </tr>
          ) : null}
        </tbody>
      </table>

      <section className="pulse-live" aria-labelledby="pulse-live-title">
        <h3 id="pulse-live-title">Сводка</h3>
        <div className="pulse-digest" data-ok={health?.ok ? "1" : "0"}>
          {digest ? (
            <>
              <p className="pulse-digest-line">{digest.summary}</p>
              <p className="pulse-digest-meta">
                {health?.ok ? "health ok" : "health down"}
                {health?.latency_ms != null ? ` · ${health.latency_ms} мс` : ""}
                {digest.generated_at ? ` · ${digest.generated_at}` : ""}
              </p>
              {ranking.length > 0 ? (
                <ul className="pulse-rank">
                  {ranking.slice(0, 4).map((row) => (
                    <li key={row.model_id}>
                      <code>{row.model_id}</code>
                      {row.score != null ? ` · ${row.score}` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <p className="pulse-digest-line">Сводки ещё нет — поставьте периодический сбор.</p>
          )}
        </div>
        <div className="pulse-jobs">
          <h3>Расписание</h3>
          {(pulse?.jobs ?? []).length === 0 ? (
            <p>Нет заданий. Агент может поставить `schedule_digest`.</p>
          ) : (
            <ul>
              {(pulse?.jobs ?? []).map((job) => (
                <li key={job.id}>
                  каждые {job.interval_seconds} с · окно {job.hours} ч
                  {job.note ? ` · ${job.note}` : ""}
                  {job.due_at ? ` · next ${job.due_at}` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="pulse-ops" aria-labelledby="pulse-ops-title">
        <h3 id="pulse-ops-title">Оператор</h3>
        <div className="pulse-presets">
          {PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className="pulse-ask"
              disabled={busy}
              onClick={() => {
                setAsk(preset.message);
                void runAsk(preset.message);
              }}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <form className="pulse-form" onSubmit={onSubmit}>
          <label className="sr-only" htmlFor="pulse-ask-input">
            Запрос оператора
          </label>
          <input
            id="pulse-ask-input"
            value={ask}
            onChange={(event) => setAsk(event.target.value)}
            disabled={busy}
            placeholder="Спросить пульс стенда"
          />
          <button type="submit" disabled={busy || !ask.trim()}>
            {busy ? "вызов…" : "Спросить"}
          </button>
        </form>
        {askError ? (
          <p className="alert" role="alert">
            {askError}
          </p>
        ) : null}
        {reply ? (
          <div className="pulse-reply">
            <p className="pulse-reply-model">
              model_id <code>{reply.model_id}</code>
            </p>
            <p className="pulse-reply-body">{reply.content}</p>
            {(reply.mcp_calls ?? []).map((call: AgentMcpCallDto) => (
              <article key={`${call.name}-${call.result.slice(0, 24)}`} className="mcp-call">
                <header>
                  <code>{call.name}</code>
                </header>
                <pre>{call.result}</pre>
              </article>
            ))}
          </div>
        ) : null}
      </section>
    </section>
  );
}

import { FormEvent, useCallback, useEffect, useState } from "react";

import {
  getMcpPulse,
  invokeMcpTool,
  listMcpTools,
  runAgentWorkshop,
  type AgentMcpCallDto,
  type AgentWorkshopRunResultDto,
  type McpCatalogDto,
  type McpPulseDto,
} from "../api/client";

const PULSE_AGENT = {
  name: "Stand Watch",
  system_prompt:
    "Ты дежурный оператор стенда. Сначала watch_brief. Потом детали: probe_stand, model_pulse, latest_digest. Ночную вахту ставь schedule_digest. Инцидент подтверждай ack_incident. Говори человеку, что делать дальше, без каталога инструментов.",
  preferred_model: "auto",
  temperature: 0.2,
  max_tokens: 700,
};

const PRESETS = [
  { id: "watch", label: "Вахта", message: "Что на вахте? Открой инциденты" },
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
  const [ask, setAsk] = useState("Что на вахте?");
  const [busy, setBusy] = useState(false);
  const [actBusy, setActBusy] = useState(false);
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

  async function runAction(name: string, args: Record<string, unknown> = {}) {
    if (actBusy) return;
    setActBusy(true);
    setAskError(null);
    try {
      await invokeMcpTool(name, args);
      await refreshPulse();
    } catch (exc) {
      setAskError(exc instanceof Error ? exc.message : "не удалось выполнить действие");
    } finally {
      setActBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void runAsk(ask);
  }

  const digest = pulse?.latest_digest;
  const health = digest?.health;
  const ranking = digest?.pulse?.ranking ?? [];
  const action = pulse?.next_action ?? pulse?.watch?.next_action;
  const probe = pulse?.watch?.latest_probe;

  return (
    <section className="mcp-board mcp-board--pulse" aria-labelledby="mcp-title">
      <header className="mcp-board-top">
        <div>
          <h2 id="mcp-title">MCP</h2>
          <p className="mcp-board-sub">
            Дежурство стенда. Пока модели отвечают посетителям, эта страница смотрит health,
            жалобы на модели и пишет ночную сводку. Агент вызывает те же MCP-инструменты.
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

      <section
        className="pulse-next"
        data-cta={action?.cta || "ok"}
        aria-labelledby="pulse-next-title"
      >
        <p className="pulse-next-kicker">Сейчас</p>
        <h3 id="pulse-next-title">{action?.title || "Снимаем пробу…"}</h3>
        <p>{action?.detail || "Вахта ещё не вернула рекомендацию."}</p>
        <div className="pulse-next-actions">
          {action?.cta === "probe" ? (
            <button type="button" className="pulse-ask" disabled={actBusy} onClick={() => void runAction("probe_stand")}>
              Проверить health
            </button>
          ) : null}
          {action?.cta === "schedule" ? (
            <button
              type="button"
              className="pulse-ask"
              disabled={actBusy}
              onClick={() =>
                void runAction("schedule_digest", {
                  interval_seconds: 3600,
                  hours: 24,
                  note: "night-watch",
                })
              }
            >
              Включить ночную вахту
            </button>
          ) : null}
          {action?.cta === "ack" && action.incident_id ? (
            <button
              type="button"
              className="pulse-ask"
              disabled={actBusy}
              onClick={() =>
                void runAction("ack_incident", {
                  incident_id: action.incident_id,
                  note: "acked from console",
                })
              }
            >
              Подтвердить инцидент
            </button>
          ) : null}
        </div>
      </section>

      <section className="pulse-watch" data-severity={pulse?.watch?.severity || "ok"}>
        <h3>Вахта</h3>
        <p className="pulse-digest-line">{pulse?.watch?.summary || "Сторож ещё не снимал пробу."}</p>
        <p className="pulse-digest-meta">
          {probe
            ? `${probe.ok ? "последняя проба ок" : "последняя проба down"}${probe.latency_ms != null ? ` · ${probe.latency_ms} мс` : ""}`
            : "проб ещё нет"}
          {pulse?.watch?.latency_delta_ms != null ? ` · Δ ${pulse.watch.latency_delta_ms} мс` : ""}
        </p>
        {(pulse?.incidents ?? []).length > 0 ? (
          <ul className="pulse-incidents">
            {(pulse?.incidents ?? []).map((item) => (
              <li key={item.id}>
                <strong>{item.severity}</strong> {item.title}
                {item.detail ? ` — ${item.detail}` : ""}
                {item.acked ? (
                  " · ack"
                ) : (
                  <>
                    {" · "}
                    <button
                      type="button"
                      className="pulse-ack"
                      disabled={actBusy}
                      onClick={() =>
                        void runAction("ack_incident", {
                          incident_id: item.id,
                          note: "acked from console",
                        })
                      }
                    >
                      подтвердить
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="pulse-digest-meta">Открытых инцидентов нет — посетители ходят на живой стенд.</p>
        )}
      </section>

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
            <p className="pulse-digest-line">Сводки ещё нет — включите ночную вахту.</p>
          )}
        </div>
        <div className="pulse-jobs">
          <h3>Расписание</h3>
          {(pulse?.jobs ?? []).length === 0 ? (
            <p>Нет заданий. Ночная вахта ещё не включена.</p>
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
        <h3 id="pulse-ops-title">Спросить дежурного</h3>
        <p className="pulse-digest-meta">
          Агент ходит в MCP и отвечает, что чинить. Не каталог — смена.
        </p>
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
            placeholder="Что сломалось, пока меня не было?"
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

      <table className="mcp-tools">
        <caption>Инструменты MCP, которыми пользуется вахта</caption>
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
    </section>
  );
}

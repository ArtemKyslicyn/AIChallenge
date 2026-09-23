import { useEffect, useState } from "react";

import { listMcpTools, type McpCatalogDto } from "../api/client";

export function McpCatalog() {
  const [data, setData] = useState<McpCatalogDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
    return () => ac.abort();
  }, []);

  return (
    <section className="mcp-board" aria-labelledby="mcp-title">
      <header className="mcp-board-top">
        <div>
          <h2 id="mcp-title">MCP</h2>
          <p className="mcp-board-sub">
            Соединение с Model Context Protocol: initialize, затем список инструментов.
            Клиент дня 16 говорит с сервером по MCP; эта страница показывает тот же каталог.
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
          </tr>
        </thead>
        <tbody>
          {(data?.tools ?? []).map((tool) => (
            <tr key={tool.name}>
              <td>
                <code>{tool.name}</code>
              </td>
              <td>{tool.description}</td>
            </tr>
          ))}
          {!loading && (data?.tools.length ?? 0) === 0 ? (
            <tr>
              <td colSpan={2}>Список пуст — сервер не ответил или токен не задан.</td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </section>
  );
}

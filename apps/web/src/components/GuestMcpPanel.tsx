import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  connectGuestMcp,
  deleteGuestMcp,
  listGuestMcp,
  patchGuestMcp,
  type GuestMcpServerDto,
} from "../api/client";

const KIT_REPO_URL = "https://github.com/ArtemKyslicyn/aichallenge-mcp-kit";
const TOOL_CHIP_CAP = 6;

function hostLabel(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function statusLabel(server: GuestMcpServerDto): string {
  if (server.status === "connected") return "Подключён";
  if (server.status === "error") return server.safe_error || "Ошибка";
  if (server.status === "off") return "Выключен";
  return server.status;
}

interface Props {
  sessionId: string;
}

export function GuestMcpPanel({ sessionId }: Props) {
  const [servers, setServers] = useState<GuestMcpServerDto[]>([]);
  const [listBusy, setListBusy] = useState(true);
  const [formOpen, setFormOpen] = useState(true);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [connectBusy, setConnectBusy] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [reconnectToken, setReconnectToken] = useState("");

  const refresh = useCallback(async () => {
    setListBusy(true);
    try {
      const list = await listGuestMcp(sessionId);
      setServers(list);
    } catch {
      setServers([]);
    } finally {
      setListBusy(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const runConnect = async (
    payload: { name: string; url: string; token: string },
    replaceId?: string,
  ) => {
    setConnectBusy(true);
    setConnectError(null);
    try {
      const server = await connectGuestMcp(sessionId, payload);
      if (replaceId && replaceId !== server.id) {
        try {
          await deleteGuestMcp(sessionId, replaceId);
        } catch {
          /* keep new server even if old delete fails */
        }
      }
      setToken("");
      setReconnectToken("");
      setExpandedId(server.id);
      await refresh();
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Не удалось подключиться к серверу.";
      setConnectError(message);
    } finally {
      setConnectBusy(false);
    }
  };

  const onSubmitNew = (e: FormEvent) => {
    e.preventDefault();
    void runConnect({ name, url, token });
  };

  const toggleEnabled = async (server: GuestMcpServerDto) => {
    try {
      const updated = await patchGuestMcp(sessionId, server.id, {
        enabled: !server.enabled,
      });
      setServers((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    } catch {
      /* ignore */
    }
  };

  const removeServer = async (server: GuestMcpServerDto) => {
    if (!window.confirm(`Удалить «${server.name}»?`)) return;
    try {
      await deleteGuestMcp(sessionId, server.id);
      if (expandedId === server.id) setExpandedId(null);
      await refresh();
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="guest-mcp-panel">
      <p className="composer-more-lead">
        Адрес с вашего компьютера. Стенд на вкладке MCP не выключается.
      </p>

      <button
        type="button"
        className="ghost-button guest-mcp-add-toggle"
        aria-expanded={formOpen}
        onClick={() => setFormOpen((open) => !open)}
      >
        Добавить по URL
      </button>

      {formOpen && (
        <form className="guest-mcp-connect-form" onSubmit={onSubmitNew}>
          <label className="composer-field">
            <span>Название</span>
            <input
              type="text"
              value={name}
              autoComplete="off"
              placeholder="Мой набор"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="composer-field">
            <span>Адрес</span>
            <input
              type="url"
              value={url}
              autoComplete="off"
              placeholder="https://…/mcp"
              required
              onChange={(e) => setUrl(e.target.value)}
            />
          </label>
          <label className="composer-field">
            <span>Токен</span>
            <input
              type="password"
              value={token}
              autoComplete="off"
              onChange={(e) => setToken(e.target.value)}
            />
          </label>
          {connectError && (
            <p className="guest-mcp-form-error" role="alert">
              {connectError}
            </p>
          )}
          <button type="submit" className="primary-button" disabled={connectBusy}>
            {connectBusy ? "Подключаем…" : "Подключить"}
          </button>
        </form>
      )}

      {listBusy && servers.length === 0 ? (
        <p className="guest-mcp-muted">Загрузка…</p>
      ) : servers.length === 0 ? (
        <p className="guest-mcp-muted">Пока нет своих серверов.</p>
      ) : (
        <ul className="guest-mcp-list">
          {servers.map((server) => {
            const expanded = expandedId === server.id;
            const toolNames = server.tool_names ?? [];
            const visibleTools = toolNames.slice(0, TOOL_CHIP_CAP);
            const moreCount = toolNames.length - visibleTools.length;
            return (
              <li key={server.id} className="guest-mcp-row">
                <div className="guest-mcp-row-head">
                  <button
                    type="button"
                    className="guest-mcp-row-toggle"
                    aria-expanded={expanded}
                    onClick={() =>
                      setExpandedId((id) => (id === server.id ? null : server.id))
                    }
                  >
                    <span className="guest-mcp-row-name">{server.name}</span>
                    <span className="guest-mcp-row-host">{hostLabel(server.url)}</span>
                  </button>
                  <span className="guest-mcp-row-status">{statusLabel(server)}</span>
                  <label className="composer-toggle guest-mcp-row-enable">
                    <input
                      type="checkbox"
                      checked={server.enabled}
                      onChange={() => void toggleEnabled(server)}
                    />
                    <span className="sr-only">Включить {server.name}</span>
                  </label>
                  <span className="guest-mcp-tool-count">
                    {toolNames.length} умений
                  </span>
                  <button
                    type="button"
                    className="ghost-button guest-mcp-delete"
                    onClick={() => void removeServer(server)}
                  >
                    Удалить
                  </button>
                </div>
                {expanded && (
                  <div className="guest-mcp-row-body">
                    {visibleTools.length > 0 && (
                      <div className="composer-options-chips" role="group" aria-label="Умения">
                        {visibleTools.map((tool) => (
                          <span key={tool} className="control-chip control-chip-muted">
                            {tool}
                          </span>
                        ))}
                        {moreCount > 0 && (
                          <span className="control-chip control-chip-muted">
                            ещё {moreCount}
                          </span>
                        )}
                      </div>
                    )}
                    <label className="composer-field">
                      <span>Токен</span>
                      <input
                        type="password"
                        value={reconnectToken}
                        autoComplete="off"
                        onChange={(e) => setReconnectToken(e.target.value)}
                      />
                    </label>
                    {connectError && expandedId === server.id && (
                      <p className="guest-mcp-form-error" role="alert">
                        {connectError}
                      </p>
                    )}
                    <button
                      type="button"
                      className="ghost-button"
                      disabled={connectBusy}
                      onClick={() =>
                        void runConnect(
                          {
                            name: server.name,
                            url: server.url,
                            token: reconnectToken,
                          },
                          server.id,
                        )
                      }
                    >
                      {connectBusy ? "Подключаем…" : "Переподключить"}
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <p className="guest-mcp-help">
        <a
          className="text-link"
          href={KIT_REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          Набор для опытов на компьютере
        </a>
      </p>
    </div>
  );
}

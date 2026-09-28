import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  authMe,
  connectGuestMcp,
  deleteGuestMcp,
  listGuestMcp,
  patchGuestMcp,
  type GuestMcpServerDto,
} from "../api/client";
import { parseGuestMcpPackText } from "../guestMcpPack";

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
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
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
  const [packText, setPackText] = useState("");
  const [packBusy, setPackBusy] = useState(false);
  const [packStatus, setPackStatus] = useState<string | null>(null);

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
    let cancelled = false;
    void authMe()
      .then((me) => {
        if (!cancelled) setSignedIn(Boolean(me && !me.anonymous && me.id));
      })
      .catch(() => {
        if (!cancelled) setSignedIn(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (signedIn !== true) {
      setServers([]);
      setListBusy(false);
      return;
    }
    void refresh();
  }, [refresh, signedIn]);

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

  const importPack = async (text: string) => {
    const parsed = parseGuestMcpPackText(text);
    if (parsed.entries.length === 0) {
      setPackStatus(
        parsed.skipped.length
          ? `Нечего подключать. ${parsed.skipped.join("; ")}`
          : "В пачке нет HTTP-серверов.",
      );
      return;
    }
    setPackBusy(true);
    setPackStatus(null);
    setConnectError(null);
    const ok: string[] = [];
    const fail: string[] = [...parsed.skipped];
    try {
      for (const entry of parsed.entries) {
        try {
          await connectGuestMcp(sessionId, entry);
          ok.push(entry.name);
        } catch (err) {
          const message =
            err instanceof ApiError
              ? err.message
              : err instanceof Error
                ? err.message
                : "ошибка";
          fail.push(`${entry.name}: ${message}`);
        }
      }
      await refresh();
      const parts: string[] = [];
      if (ok.length) parts.push(`Подключено: ${ok.join(", ")}`);
      if (fail.length) parts.push(`Пропущено: ${fail.join("; ")}`);
      setPackStatus(parts.join(". ") || null);
      if (ok.length) setPackText("");
    } finally {
      setPackBusy(false);
    }
  };

  const onPackFile = (file: File | null) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === "string" ? reader.result : "";
      setPackText(text);
      void importPack(text);
    };
    reader.onerror = () => setPackStatus("Не удалось прочитать файл.");
    reader.readAsText(file);
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

  const howTo = (
    <ol className="guest-mcp-steps">
      <li>Справа в шапке нажмите Войти (если ещё не вошли).</li>
      <li>Вставьте адрес своего MCP — обычно заканчивается на /mcp — и нажмите Подключить.</li>
      <li>Закройте настройки и пишите в обычный чат: модель сама вызовет умения.</li>
    </ol>
  );

  if (signedIn !== true) {
    return (
      <div className="guest-mcp-panel">
        <p className="composer-more-lead">Свой MCP — не вкладка MCP. Там стенд.</p>
        {howTo}
        <p className="guest-mcp-muted">
          {signedIn === null ? "Проверяем вход…" : "Сначала войдите — форма появится здесь."}
        </p>
      </div>
    );
  }

  const ready = servers.some((s) => s.enabled && s.status === "connected");

  return (
    <div className="guest-mcp-panel">
      <p className="composer-more-lead">Свой MCP — не вкладка MCP. Там стенд.</p>
      {howTo}
      {ready ? (
        <p className="guest-mcp-ready" role="status">
          Сервер на связи. Пишите в обычный чат обычным языком. Строка «Вызываю … на вашем
          сервере» значит, что умение сработало.
        </p>
      ) : null}

      <button
        type="button"
        className="ghost-button guest-mcp-add-toggle"
        aria-expanded={formOpen}
        onClick={() => setFormOpen((open) => !open)}
      >
        {formOpen ? "Скрыть форму" : "Вставить адрес MCP"}
      </button>

      {formOpen && (
        <form className="guest-mcp-connect-form" onSubmit={onSubmitNew}>
          <label className="composer-field">
            <span>Название (необязательно)</span>
            <input
              type="text"
              value={name}
              autoComplete="off"
              placeholder="Мой набор"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="composer-field">
            <span>Адрес MCP</span>
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
            <span>Токен (если сервер его просит)</span>
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

      <div className="guest-mcp-pack">
        <p className="composer-more-lead">Или пачка JSON (несколько MCP сразу)</p>
        <p className="guest-mcp-muted">
          Формат Cursor <code>mcpServers</code> или наш <code>servers[]</code>. Stdio
          (command) с ноутбука сюда не лезет — нужен HTTPS-туннель на /mcp.
        </p>
        <label className="composer-field">
          <span>Файл .json</span>
          <input
            type="file"
            accept="application/json,.json"
            disabled={packBusy || connectBusy}
            onChange={(e) => onPackFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <label className="composer-field">
          <span>Или вставить JSON</span>
          <textarea
            className="composer-rules-input guest-mcp-pack-text"
            rows={4}
            value={packText}
            spellCheck={false}
            autoComplete="off"
            placeholder='{"servers":[{"name":"kit","url":"https://…/mcp","token":""}]}'
            onChange={(e) => setPackText(e.target.value)}
          />
        </label>
        {packStatus ? (
          <p className="guest-mcp-muted" role="status">
            {packStatus}
          </p>
        ) : null}
        <button
          type="button"
          className="ghost-button"
          disabled={packBusy || connectBusy || !packText.trim()}
          onClick={() => void importPack(packText)}
        >
          {packBusy ? "Подключаем пачку…" : "Подключить пачку"}
        </button>
      </div>

      {listBusy && servers.length === 0 ? (
        <p className="guest-mcp-muted">Загрузка…</p>
      ) : servers.length === 0 ? (
        <p className="guest-mcp-muted">Пока нет своего MCP. Вставьте адрес выше и нажмите Подключить.</p>
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

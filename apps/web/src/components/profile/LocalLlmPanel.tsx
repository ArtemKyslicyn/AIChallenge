import { useEffect, useRef, useState, type FormEvent } from "react";

import { useAuthUser } from "../../auth/authUser";
import {
  ApiError,
  deleteLocalLlmSource,
  emitLocalLlmChanged,
  getLocalLlmSource,
  putLocalLlmSource,
  type LocalLlmSourceDto,
} from "../../api/client";

const ADDRESS_HINT =
  "M1 http://100.90.210.109:11435. Туннель: http://127.0.0.1:21434. Этот Mac: http://127.0.0.1:11434.";

function connectedLine(source: LocalLlmSourceDto): string {
  return `Подключено: ${source.base_host}. Моделей: ${source.models.length}.`;
}

export function LocalLlmPanel() {
  const { user } = useAuthUser();
  const signedIn = Boolean(user && !user.anonymous && user.id);
  const [source, setSource] = useState<LocalLlmSourceDto | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);

  useEffect(() => {
    if (!signedIn) {
      setSource(null);
      setFormOpen(false);
      setStatus("");
      return;
    }
    let cancelled = false;
    void getLocalLlmSource()
      .then((row) => {
        if (cancelled) return;
        setSource(row);
        setStatus(row ? connectedLine(row) : "Не подключена.");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setSource(null);
        setStatus("");
        if (err instanceof ApiError && err.status === 401) {
          setError("Сначала войдите.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [signedIn]);

  if (!signedIn) {
    return (
      <section className="profile-form" aria-labelledby="local-llm-title">
        <h3 id="local-llm-title">Локальная модель (Ollama)</h3>
        <p role="status">Сначала войдите.</p>
      </section>
    );
  }

  const onSave = (event: FormEvent) => {
    event.preventDefault();
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setError("");
    const body: { name: string; base_url: string; api_key?: string } = {
      name: name.trim(),
      base_url: baseUrl.trim(),
    };
    const key = apiKey.trim();
    if (key) body.api_key = key;
    void putLocalLlmSource(body)
      .then((row) => {
        setSource(row);
        setFormOpen(false);
        setApiKey("");
        setStatus(connectedLine(row));
        emitLocalLlmChanged();
      })
      .catch((err: unknown) => {
        const message = err instanceof ApiError ? err.message : "Ollama недоступен по этому адресу.";
        setError(message);
      })
      .finally(() => {
        saving.current = false;
        setBusy(false);
      });
  };

  const onDelete = () => {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setError("");
    void deleteLocalLlmSource()
      .then(() => {
        setSource(null);
        setFormOpen(false);
        setName("");
        setBaseUrl("");
        setApiKey("");
        setStatus("Не подключена.");
        emitLocalLlmChanged();
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "Не удалось удалить.");
      })
      .finally(() => {
        saving.current = false;
        setBusy(false);
      });
  };

  const showConnect = source === null && !formOpen;
  const showFields = source === null && formOpen;

  return (
    <section className="profile-form" aria-labelledby="local-llm-title">
      <h3 id="local-llm-title">Локальная модель (Ollama)</h3>
      <p role="status" aria-live="polite">
        {status}
      </p>
      {error ? (
        <p role="alert" className="alert">
          {error}
        </p>
      ) : null}
      {showConnect ? (
        <button type="button" className="primary-button" onClick={() => setFormOpen(true)}>
          Подключить
        </button>
      ) : null}
      {showFields ? (
        <form onSubmit={onSave}>
          <label className="composer-field">
            <span>Название</span>
            <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} />
          </label>
          <label className="composer-field">
            <span>Адрес Ollama</span>
            <input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              required
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          <p className="guest-mcp-muted">{ADDRESS_HINT}</p>
          <label className="composer-field">
            <span>Ключ (необязательно)</span>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="new-password"
            />
          </label>
          <button type="submit" className="primary-button" aria-busy={busy || undefined}>
            Сохранить
          </button>
        </form>
      ) : null}
      {source ? (
        <button
          type="button"
          className="ghost-button"
          aria-label="Удалить локальную модель"
          onClick={onDelete}
        >
          Удалить
        </button>
      ) : null}
    </section>
  );
}

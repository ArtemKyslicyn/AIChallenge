import { useCallback, useEffect, useId, useRef, useState } from "react";

import {
  deleteAnyRagDocument,
  deleteSessionRagDocument,
  emitRagIngested,
  fetchRagAdminEligible,
  fetchRagStats,
  healRag,
  listAllRagDocuments,
  listSessionRagDocuments,
  uploadRagDocumentForSession,
  type RagDocumentListItemDto,
  type RagStatsDto,
} from "../api/client";

interface Props {
  sessionId: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function RagFloat({ sessionId, open: openProp, onOpenChange }: Props) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const controlled = openProp !== undefined;
  const open = controlled ? openProp : uncontrolledOpen;
  const setOpen = (next: boolean) => {
    if (!controlled) setUncontrolledOpen(next);
    onOpenChange?.(next);
  };

  const [stats, setStats] = useState<RagStatsDto | null>(null);
  const [docs, setDocs] = useState<RagDocumentListItemDto[]>([]);
  const [admin, setAdmin] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const fabRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const focusOnOpen = useRef(false);

  const collapse = useCallback(
    (owned: boolean) => {
      if (!controlled) setUncontrolledOpen(false);
      onOpenChange?.(false);
      if (owned) queueMicrotask(() => fabRef.current?.focus());
    },
    [controlled, onOpenChange],
  );

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [s, eligible] = await Promise.all([
        fetchRagStats(),
        fetchRagAdminEligible().catch(() => ({ eligible: false })),
      ]);
      setStats(s);
      setAdmin(Boolean(eligible.eligible));
      const list =
        eligible.eligible && showAll
          ? await listAllRagDocuments()
          : await listSessionRagDocuments(sessionId);
      setDocs(list.documents || []);
      setHint(
        eligible.eligible && showAll
          ? `Всего документов: ${list.count}`
          : `Мои загрузки: ${list.count}`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить базу");
    } finally {
      setBusy(false);
    }
  }, [sessionId, showAll]);

  useEffect(() => {
    if (!open) return;
    void refresh();
  }, [open, refresh]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      collapse(panelRef.current?.contains(document.activeElement) ?? false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, collapse]);

  useEffect(() => {
    if (!open || !focusOnOpen.current) return;
    focusOnOpen.current = false;
    queueMicrotask(() => panelRef.current?.focus());
  }, [open]);

  const onUpload = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setHint(`Добавляем «${file.name}»…`);
    try {
      const result = await uploadRagDocumentForSession(sessionId, file);
      emitRagIngested({ ...result, filename: result.filename || file.name });
      setHint(`Добавлено · +${result.added_chunks ?? 0} чанков`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (doc: RagDocumentListItemDto) => {
    if (!window.confirm(`Удалить «${doc.title || doc.source}» из базы?`)) return;
    setBusy(true);
    setError(null);
    try {
      if (admin && showAll) {
        await deleteAnyRagDocument(doc.source, {
          scope: doc.scope,
          ownerId: doc.owner_id,
        });
      } else {
        await deleteSessionRagDocument(sessionId, doc.source);
      }
      setHint(`Удалено: ${doc.source}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить");
    } finally {
      setBusy(false);
    }
  };

  const onForceHeal = async () => {
    if (
      !window.confirm(
        "Пересобрать эмбеддинги через API? Это займёт несколько минут; поиск может временно просесть.",
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    setHint("Пересобираем эмбеддинги…");
    try {
      const result = await healRag(true);
      setHint(
        `Heal: ${String(result.healed)} · embed ${result.embed_model || result.embed_model_runtime || "—"} · vectors ${result.vector_count ?? "—"}`,
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Heal не удался");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="debug-float-root rag-float-root">
      {!open && (
        <button
          ref={fabRef}
          type="button"
          className="debug-float-fab rag-float-fab"
          aria-label="База знаний"
          onClick={() => {
            focusOnOpen.current = true;
            setOpen(true);
          }}
        >
          База
          {docs.length > 0 ? (
            <span className="debug-float-badge" aria-hidden="true">
              {docs.length}
            </span>
          ) : null}
        </button>
      )}

      {open && (
        <aside
          ref={panelRef}
          className="debug-float rag-float"
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          tabIndex={-1}
        >
          <header className="debug-float-head">
            <h2 id={titleId} className="debug-float-title">
              База знаний
              <span className="debug-float-live" aria-hidden="true" />
            </h2>
            <div className="debug-float-actions">
              <button
                type="button"
                className="ghost-button"
                disabled={busy}
                onClick={() => void refresh()}
              >
                Обновить
              </button>
              <button
                type="button"
                className="ghost-button"
                disabled={busy}
                onClick={() => fileRef.current?.click()}
              >
                Загрузить
              </button>
              <button
                type="button"
                className="ghost-button"
                aria-label="Свернуть панель базы"
                onClick={() => collapse(true)}
              >
                Свернуть
              </button>
            </div>
          </header>

          <div className="rag-float-body">
            <p className="rag-float-stats">
              {stats?.disabled
                ? "Сервис базы недоступен."
                : `Чанков: ${stats?.total_chunks ?? "…"} · ${stats?.chunk_strategy ?? "—"} · embed ${stats?.embed_model || stats?.embedding_provider || "—"} · vectors ${stats?.vector_count ?? "—"}`}
            </p>

            {admin ? (
              <div className="rag-float-admin-row">
                <label className="composer-toggle rag-float-admin-toggle">
                  <input
                    type="checkbox"
                    checked={showAll}
                    onChange={(e) => setShowAll(e.target.checked)}
                  />
                  <span>Все документы (админ)</span>
                </label>
                <button
                  type="button"
                  className="ghost-button"
                  disabled={busy}
                  onClick={() => void onForceHeal()}
                >
                  {stats?.embed_model === "fake-hash"
                    ? "Пересобрать API-эмбеддинги"
                    : "Force heal"}
                </button>
              </div>
            ) : null}

            <input
              ref={fileRef}
              type="file"
              accept=".md,.txt,.pdf,.rst,.py,.ts,.tsx,.yml,.yaml,.json"
              hidden
              onChange={(e) => {
                void onUpload(e.target.files);
                e.target.value = "";
              }}
            />

            {hint ? <p className="composer-rag-hint">{hint}</p> : null}
            {error ? (
              <p className="alert" role="alert">
                {error}
              </p>
            ) : null}

            <ul className="rag-float-docs">
              {docs.length === 0 ? (
                <li className="debug-float-empty">
                  Своих загрузок нет. Стендовый корпус в поиске остаётся. Загрузите файл или удалите
                  ненужный после добавления.
                </li>
              ) : (
                docs.map((doc) => (
                  <li key={`${doc.scope}:${doc.owner_id}:${doc.source}`} className="rag-float-doc">
                    <div className="rag-float-doc-main">
                      <strong>{doc.title || doc.source}</strong>
                      <span className="rag-sources-meta">
                        {" "}
                        · {doc.chunk_count} чанк. · {doc.scope}
                        {doc.strategy ? ` · ${doc.strategy}` : ""}
                      </span>
                      {doc.preview ? <pre>{doc.preview}</pre> : null}
                    </div>
                    {(doc.scope === "session" || (admin && showAll)) && (
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={busy}
                        onClick={() => void onDelete(doc)}
                      >
                        Удалить
                      </button>
                    )}
                  </li>
                ))
              )}
            </ul>
          </div>
        </aside>
      )}
    </div>
  );
}

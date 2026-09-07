import { useEffect, useId, useMemo, useRef, useState } from "react";

import {
  ApiError,
  listModels,
  runAgentWorkshop,
  type ModelCatalogItemDto,
} from "../api/client";
import {
  blankDraft,
  canAddDraft,
  duplicateDraft,
  loadDraftStore,
  saveDraftStore,
  type AgentDraft,
  type AgentDraftStore,
  MAX_DRAFTS,
} from "../agents/drafts";
import { AGENT_PRESETS } from "../agents/presets";
import {
  emptySession,
  ensureSession,
  loadSessions,
  saveSessions,
  type AgentSession,
  type RunLine,
} from "../agents/sessions";

function draftById(store: AgentDraftStore, id: string): AgentDraft | undefined {
  return store.drafts.find((d) => d.id === id);
}

export function AgentWorkshop() {
  const titleId = useId();
  const [store, setStore] = useState<AgentDraftStore>(() =>
    loadDraftStore(blankDraft(AGENT_PRESETS[0])),
  );
  const [sessions, setSessions] = useState<Record<string, AgentSession>>(() => loadSessions());
  const [busyIds, setBusyIds] = useState<Record<string, boolean>>({});
  const [savedFlash, setSavedFlash] = useState(false);
  const [models, setModels] = useState<ModelCatalogItemDto[]>([]);
  const [mobileSheet, setMobileSheet] = useState(false);
  const [libraryQuery, setLibraryQuery] = useState("");
  const abortMap = useRef<Map<string, AbortController>>(new Map());
  const saveTimer = useRef<number | null>(null);
  const sessionTimer = useRef<number | null>(null);

  const active = draftById(store, store.activeId) ?? store.drafts[0];
  const panelIds = store.panelIds.length ? store.panelIds : [store.activeId];
  const split = panelIds.length > 1;

  useEffect(() => {
    listModels()
      .then(setModels)
      .catch(() => setModels([]));
  }, []);

  useEffect(() => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      saveDraftStore(store);
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 1200);
    }, 350);
    return () => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
    };
  }, [store]);

  useEffect(() => {
    if (sessionTimer.current) window.clearTimeout(sessionTimer.current);
    sessionTimer.current = window.setTimeout(() => saveSessions(sessions), 200);
    return () => {
      if (sessionTimer.current) window.clearTimeout(sessionTimer.current);
    };
  }, [sessions]);

  useEffect(() => {
    return () => {
      for (const c of abortMap.current.values()) c.abort();
      abortMap.current.clear();
    };
  }, []);

  const modelOptions = useMemo(() => {
    const ids = new Set(models.map((m) => m.id));
    if (!ids.has("auto")) return [{ id: "auto", label: "auto" }, ...models];
    return models;
  }, [models]);

  const filteredDrafts = useMemo(() => {
    const q = libraryQuery.trim().toLowerCase();
    if (!q) return store.drafts;
    return store.drafts.filter(
      (d) =>
        d.name.toLowerCase().includes(q) ||
        d.system_prompt.toLowerCase().includes(q),
    );
  }, [store.drafts, libraryQuery]);

  function patchSession(id: string, patch: Partial<AgentSession>) {
    setSessions((prev) => ({
      ...prev,
      [id]: { ...ensureSession(prev, id), ...patch },
    }));
  }

  function appendLog(id: string, line: RunLine) {
    setSessions((prev) => {
      const cur = ensureSession(prev, id);
      return { ...prev, [id]: { ...cur, log: [...cur.log, line] } };
    });
  }

  function patchDraft(id: string, patch: Partial<AgentDraft>) {
    setStore((prev) => ({
      ...prev,
      drafts: prev.drafts.map((d) =>
        d.id === id ? { ...d, ...patch, updatedAt: Date.now() } : d,
      ),
    }));
  }

  function focusAgent(id: string) {
    setStore((prev) => {
      const panelIds = prev.panelIds.includes(id)
        ? prev.panelIds
        : [id, ...prev.panelIds.filter((x) => x !== id)].slice(0, 2);
      return { ...prev, activeId: id, panelIds: split ? panelIds : [id] };
    });
    setMobileSheet(false);
  }

  function openSplitWith(id: string) {
    setStore((prev) => {
      const primary = prev.activeId;
      if (id === primary) return prev;
      return { ...prev, activeId: id, panelIds: [primary, id].slice(0, 2) };
    });
  }

  function closeSplit() {
    setStore((prev) => ({ ...prev, panelIds: [prev.activeId] }));
  }

  function newDraft(from?: Partial<AgentDraft>) {
    if (!canAddDraft(store)) {
      window.alert(`Лимит ${MAX_DRAFTS} агентов. Удалите лишние.`);
      return;
    }
    const next = blankDraft(from);
    setSessions((prev) => ({ ...prev, [next.id]: emptySession() }));
    setStore((prev) => ({
      activeId: next.id,
      panelIds: split ? [next.id, ...prev.panelIds].slice(0, 2) : [next.id],
      drafts: [next, ...prev.drafts],
    }));
  }

  function createFromPreset(index: number) {
    const preset = AGENT_PRESETS[index];
    if (!preset) return;
    newDraft(preset);
  }

  function onDuplicate(id: string) {
    const source = draftById(store, id);
    if (!source) return;
    if (!canAddDraft(store)) {
      window.alert(`Лимит ${MAX_DRAFTS} агентов.`);
      return;
    }
    const next = duplicateDraft(source);
    setSessions((prev) => ({ ...prev, [next.id]: emptySession() }));
    setStore((prev) => ({
      activeId: next.id,
      panelIds: split ? [next.id, prev.activeId].slice(0, 2) : [next.id],
      drafts: [next, ...prev.drafts],
    }));
  }

  function onDelete(id: string) {
    if (store.drafts.length <= 1) {
      window.alert("Нужен хотя бы один агент.");
      return;
    }
    const d = draftById(store, id);
    if (!d || !window.confirm(`Удалить «${d.name}»?`)) return;
    abortMap.current.get(id)?.abort();
    abortMap.current.delete(id);
    setBusyIds((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    setSessions((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    setStore((prev) => {
      const drafts = prev.drafts.filter((x) => x.id !== id);
      const activeId = prev.activeId === id ? drafts[0].id : prev.activeId;
      const panelIds = prev.panelIds.filter((x) => x !== id);
      return {
        drafts,
        activeId,
        panelIds: panelIds.length ? panelIds : [activeId],
      };
    });
  }

  function clearLog(id: string) {
    patchSession(id, { log: [], status: "" });
  }

  async function send(agentId: string) {
    const draft = draftById(store, agentId);
    const session = ensureSession(sessions, agentId);
    const message = session.input.trim();
    if (!draft || !message || busyIds[agentId]) return;
    if (!draft.system_prompt.trim()) {
      patchSession(agentId, { status: "Заполните инструкцию агента." });
      setStore((prev) => ({ ...prev, activeId: agentId }));
      setMobileSheet(true);
      return;
    }

    appendLog(agentId, { id: `u-${Date.now()}`, role: "user", text: message });
    patchSession(agentId, { input: "", status: "Ждём ответ…" });
    setBusyIds((prev) => ({ ...prev, [agentId]: true }));

    const controller = new AbortController();
    abortMap.current.get(agentId)?.abort();
    abortMap.current.set(agentId, controller);

    try {
      const result = await runAgentWorkshop(
        {
          name: draft.name,
          system_prompt: draft.system_prompt,
          preferred_model: draft.preferred_model || "auto",
          temperature: draft.temperature,
          max_tokens: draft.max_tokens,
        },
        message,
        controller.signal,
      );
      appendLog(agentId, {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: result.content,
        modelId: result.model_id,
      });
      patchSession(agentId, { status: "" });
    } catch (e) {
      if (controller.signal.aborted) {
        appendLog(agentId, {
          id: `s-${Date.now()}`,
          role: "status",
          text: "Запрос отменён.",
        });
        patchSession(agentId, { status: "" });
      } else {
        const msg =
          e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
        appendLog(agentId, { id: `e-${Date.now()}`, role: "error", text: msg });
        patchSession(agentId, { status: "Не удалось получить ответ." });
      }
    } finally {
      setBusyIds((prev) => {
        const next = { ...prev };
        delete next[agentId];
        return next;
      });
      abortMap.current.delete(agentId);
    }
  }

  function stop(agentId: string) {
    abortMap.current.get(agentId)?.abort();
  }

  const builder = (draft: AgentDraft) => (
    <div className="agent-builder">
      <header className="agent-builder-head">
        <h3>Кто отвечает</h3>
        <p className="agent-hint">Имя и инструкция сохраняются сами в этом браузере.</p>
      </header>
      <label className="agent-field">
        <span>Имя</span>
        <input
          value={draft.name}
          onChange={(e) => patchDraft(draft.id, { name: e.target.value })}
          maxLength={120}
        />
      </label>
      <label className="agent-field agent-field--grow">
        <span>Инструкция агента</span>
        <textarea
          value={draft.system_prompt}
          onChange={(e) => patchDraft(draft.id, { system_prompt: e.target.value })}
          rows={split ? 6 : 12}
          spellCheck
        />
      </label>
      <fieldset className="agent-how">
        <legend>Как отвечает</legend>
        <label className="agent-field">
          <span>Модель</span>
          <select
            value={draft.preferred_model}
            onChange={(e) => patchDraft(draft.id, { preferred_model: e.target.value })}
          >
            {modelOptions.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label || m.id}
              </option>
            ))}
          </select>
        </label>
        <div className="agent-how-row">
          <label className="agent-field">
            <span>Temp</span>
            <input
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={draft.temperature ?? 0.7}
              onChange={(e) => patchDraft(draft.id, { temperature: Number(e.target.value) })}
            />
          </label>
          <label className="agent-field">
            <span>Max tokens</span>
            <input
              type="number"
              min={1}
              max={8192}
              step={1}
              value={draft.max_tokens ?? 512}
              onChange={(e) => patchDraft(draft.id, { max_tokens: Number(e.target.value) })}
            />
          </label>
        </div>
      </fieldset>
      <div className="agent-builder-actions">
        <button type="button" className="ghost-button" onClick={() => onDuplicate(draft.id)}>
          Дублировать
        </button>
        <button type="button" className="ghost-button" onClick={() => clearLog(draft.id)}>
          Очистить лог
        </button>
        <span className="agent-save" aria-live="polite">
          {savedFlash ? "Сохранено" : "Автосохранение"}
        </span>
      </div>
    </div>
  );

  const panel = (agentId: string) => {
    const draft = draftById(store, agentId);
    if (!draft) return null;
    const session = ensureSession(sessions, agentId);
    const busy = Boolean(busyIds[agentId]);
    const focused = store.activeId === agentId;

    return (
      <article
        key={agentId}
        className={`agent-panel${focused ? " agent-panel--focus" : ""}`}
        onClick={() => {
          if (!focused) setStore((prev) => ({ ...prev, activeId: agentId }));
        }}
      >
        <header className="agent-panel-head">
          <div className="agent-panel-title">
            <strong>{draft.name}</strong>
            {busy ? <span className="agent-busy-dot" title="Идёт запрос" /> : null}
          </div>
          <div className="agent-panel-tools">
            {!split ? (
              <button
                type="button"
                className="ghost-button"
                disabled={store.drafts.length < 2}
                onClick={(e) => {
                  e.stopPropagation();
                  const other = store.drafts.find((d) => d.id !== agentId);
                  if (other) openSplitWith(other.id);
                }}
                title="Открыть второго агента рядом"
              >
                + Рядом
              </button>
            ) : (
              <button
                type="button"
                className="ghost-button"
                onClick={(e) => {
                  e.stopPropagation();
                  if (panelIds.length === 2 && panelIds[0] !== agentId) {
                    setStore((prev) => ({
                      ...prev,
                      activeId: agentId,
                      panelIds: [agentId],
                    }));
                  } else {
                    closeSplit();
                  }
                }}
              >
                Закрыть панель
              </button>
            )}
            <button
              type="button"
              className="ghost-button agent-mobile-settings"
              onClick={(e) => {
                e.stopPropagation();
                setStore((prev) => ({ ...prev, activeId: agentId }));
                setMobileSheet(true);
              }}
            >
              Настройки
            </button>
          </div>
        </header>

        {!split ? (
          <div className="agent-panel-split">
            <aside className="agent-workshop-builder desktop-only">{builder(draft)}</aside>
            <div className="agent-workshop-dialog">{dialogBody(draft, session, busy)}</div>
          </div>
        ) : (
          <div className="agent-panel-compact">
            <details className="agent-panel-settings">
              <summary>Инструкция и модель</summary>
              {builder(draft)}
            </details>
            <div className="agent-workshop-dialog">{dialogBody(draft, session, busy)}</div>
          </div>
        )}
      </article>
    );
  };

  function dialogBody(draft: AgentDraft, session: AgentSession, busy: boolean) {
    return (
      <>
        <div className="agent-log" aria-live="polite">
          {session.log.length === 0 ? (
            <div className="agent-log-empty">
              <p>
                Прогоны этого агента не мешают другим — можно слать запросы параллельно.
                Лог держится, пока открыта вкладка браузера.
              </p>
              <button
                type="button"
                className="chip"
                onClick={() =>
                  patchSession(draft.id, {
                    input: "Сократи этот текст: ну короче это типа важно",
                  })
                }
              >
                Пример: сократи текст
              </button>
            </div>
          ) : (
            session.log.map((line) => (
              <article key={line.id} className={`agent-log-line agent-log-line--${line.role}`}>
                {line.role === "assistant" && line.modelId ? (
                  <span className="badge">{line.modelId}</span>
                ) : null}
                <p>{line.text}</p>
              </article>
            ))
          )}
        </div>
        {session.status ? (
          <p className="agent-status" role="status">
            {session.status}
          </p>
        ) : null}
        <form
          className="agent-compose"
          onSubmit={(e) => {
            e.preventDefault();
            void send(draft.id);
          }}
        >
          <textarea
            value={session.input}
            onChange={(e) => patchSession(draft.id, { input: e.target.value })}
            rows={2}
            placeholder={`Сообщение → ${draft.name}`}
            disabled={false}
            onClick={(e) => e.stopPropagation()}
          />
          {busy ? (
            <button
              type="button"
              className="agent-send-btn"
              onClick={(e) => {
                e.stopPropagation();
                stop(draft.id);
              }}
            >
              Стоп
            </button>
          ) : (
            <button
              type="submit"
              className="agent-send-btn"
              disabled={!session.input.trim()}
              onClick={(e) => e.stopPropagation()}
            >
              Отправить
            </button>
          )}
        </form>
      </>
    );
  }

  return (
    <section className={`agent-workshop${split ? " agent-workshop--split" : ""}`} aria-labelledby={titleId}>
      <header className="agent-workshop-top">
        <div className="agent-workshop-title-row">
          <h2 id={titleId}>Агенты</h2>
          <p className="agent-workshop-lead">
            Несколько агентов · параллельные запросы · автосохранение настроек
          </p>
        </div>
        <div className="agent-presets" role="group" aria-label="Пресеты">
          {AGENT_PRESETS.map((p, i) => (
            <button key={p.name} type="button" className="chip" onClick={() => createFromPreset(i)}>
              + {p.name}
            </button>
          ))}
          <button type="button" className="chip" onClick={() => newDraft()}>
            + Пустой
          </button>
        </div>
      </header>

      <div className="agent-workshop-layout">
        <aside className="agent-rail" aria-label="Список агентов">
          <div className="agent-rail-head">
            <input
              className="agent-rail-search"
              value={libraryQuery}
              onChange={(e) => setLibraryQuery(e.target.value)}
              placeholder="Найти агента…"
              aria-label="Поиск агентов"
            />
            <button type="button" className="ghost-button" onClick={() => newDraft()} title="Новый">
              +
            </button>
          </div>
          <ul className="agent-rail-list">
            {filteredDrafts.map((d) => {
              const busy = Boolean(busyIds[d.id]);
              const inPanel = panelIds.includes(d.id);
              return (
                <li key={d.id}>
                  <button
                    type="button"
                    className={`agent-rail-item${store.activeId === d.id ? " is-active" : ""}${
                      inPanel ? " is-open" : ""
                    }`}
                    onClick={() => focusAgent(d.id)}
                  >
                    <span className="agent-rail-name">{d.name}</span>
                    {busy ? <span className="agent-busy-dot" /> : null}
                  </button>
                  <div className="agent-rail-item-actions">
                    {split && !inPanel ? (
                      <button
                        type="button"
                        className="ghost-button"
                        title="Открыть рядом"
                        onClick={() => openSplitWith(d.id)}
                      >
                        ‖
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="ghost-button"
                      title="Дублировать"
                      onClick={() => onDuplicate(d.id)}
                    >
                      ⎘
                    </button>
                    <button
                      type="button"
                      className="ghost-button"
                      title="Удалить"
                      onClick={() => onDelete(d.id)}
                    >
                      ×
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="agent-rail-foot">
            {store.drafts.length}/{MAX_DRAFTS}
            {split ? " · split" : ""}
          </p>
        </aside>

        <div className={`agent-panels${split ? " agent-panels--split" : ""}`}>
          {panelIds.map((id) => panel(id))}
        </div>
      </div>

      {mobileSheet && active ? (
        <div className="agent-sheet" role="dialog" aria-modal="true" aria-label="Настройки агента">
          <div className="agent-sheet-backdrop" onClick={() => setMobileSheet(false)} />
          <div className="agent-sheet-panel">
            <header className="agent-sheet-head">
              <h3>{active.name}</h3>
              <button type="button" className="ghost-button" onClick={() => setMobileSheet(false)}>
                Закрыть
              </button>
            </header>
            {builder(active)}
          </div>
        </div>
      ) : null}
    </section>
  );
}

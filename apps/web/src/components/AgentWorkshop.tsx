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
  loadDraftStore,
  saveDraftStore,
  type AgentDraft,
  type AgentDraftStore,
  MAX_DRAFTS,
} from "../agents/drafts";
import { AGENT_PRESETS } from "../agents/presets";

interface RunLine {
  id: string;
  role: "user" | "assistant" | "error" | "status";
  text: string;
  modelId?: string | null;
}

function activeDraft(store: AgentDraftStore): AgentDraft {
  return store.drafts.find((d) => d.id === store.activeId) ?? store.drafts[0];
}

export function AgentWorkshop() {
  const titleId = useId();
  const liveId = useId();
  const [store, setStore] = useState<AgentDraftStore>(() =>
    loadDraftStore(blankDraft(AGENT_PRESETS[0])),
  );
  const [savedFlash, setSavedFlash] = useState(false);
  const [models, setModels] = useState<ModelCatalogItemDto[]>([]);
  const [log, setLog] = useState<RunLine[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [mobileSheet, setMobileSheet] = useState(false);
  const [status, setStatus] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const saveTimer = useRef<number | null>(null);
  const draft = activeDraft(store);

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
      window.setTimeout(() => setSavedFlash(false), 900);
    }, 400);
    return () => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
    };
  }, [store]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const modelOptions = useMemo(() => {
    const ids = new Set(models.map((m) => m.id));
    if (!ids.has("auto")) {
      return [{ id: "auto", label: "auto" }, ...models];
    }
    return models;
  }, [models]);

  function patchDraft(patch: Partial<AgentDraft>) {
    setStore((prev) => ({
      ...prev,
      drafts: prev.drafts.map((d) =>
        d.id === prev.activeId ? { ...d, ...patch, updatedAt: Date.now() } : d,
      ),
    }));
  }

  function switchDraft(id: string) {
    if (id === store.activeId) return;
    if (log.length > 0) {
      const ok = window.confirm("Сменить агента и очистить лог прогонов?");
      if (!ok) return;
    }
    setLog([]);
    setStore((prev) => ({ ...prev, activeId: id }));
    setMobileSheet(false);
  }

  function createFromPreset(presetIndex: number) {
    const preset = AGENT_PRESETS[presetIndex];
    if (!preset) return;
    if (!canAddDraft(store)) {
      window.alert(`Лимит ${MAX_DRAFTS} черновиков. Удалите один, чтобы добавить новый.`);
      return;
    }
    if (log.length > 0) {
      const ok = window.confirm("Создать черновик из пресета и очистить лог?");
      if (!ok) return;
    }
    const next = blankDraft(preset);
    setLog([]);
    setStore((prev) => ({
      activeId: next.id,
      drafts: [next, ...prev.drafts],
    }));
    setMobileSheet(false);
  }

  function newDraft() {
    if (!canAddDraft(store)) {
      window.alert(`Лимит ${MAX_DRAFTS} черновиков. Удалите один, чтобы добавить новый.`);
      return;
    }
    if (log.length > 0 && !window.confirm("Создать нового агента и очистить лог?")) return;
    const next = blankDraft({ name: "Новый агент", system_prompt: "" });
    setLog([]);
    setStore((prev) => ({ activeId: next.id, drafts: [next, ...prev.drafts] }));
  }

  function deleteDraft() {
    if (store.drafts.length <= 1) {
      window.alert("Нужен хотя бы один черновик.");
      return;
    }
    if (!window.confirm(`Удалить «${draft.name}»?`)) return;
    setLog([]);
    setStore((prev) => {
      const drafts = prev.drafts.filter((d) => d.id !== prev.activeId);
      return { activeId: drafts[0].id, drafts };
    });
  }

  function renameDraft() {
    const name = window.prompt("Имя агента", draft.name);
    if (name == null) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    patchDraft({ name: trimmed.slice(0, 120) });
  }

  async function send() {
    const message = input.trim();
    if (!message || busy) return;
    if (!draft.system_prompt.trim()) {
      setStatus("Сначала заполните инструкцию агента.");
      setMobileSheet(true);
      return;
    }
    const userLine: RunLine = {
      id: `u-${Date.now()}`,
      role: "user",
      text: message,
    };
    setLog((prev) => [...prev, userLine]);
    setInput("");
    setBusy(true);
    setStatus("Ждём ответ…");
    const controller = new AbortController();
    abortRef.current = controller;
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
      setLog((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: result.content,
          modelId: result.model_id,
        },
      ]);
      setStatus("");
    } catch (e) {
      if (controller.signal.aborted) {
        setLog((prev) => [
          ...prev,
          { id: `s-${Date.now()}`, role: "status", text: "Запрос отменён." },
        ]);
        setStatus("");
      } else {
        const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
        setLog((prev) => [
          ...prev,
          { id: `e-${Date.now()}`, role: "error", text: msg },
        ]);
        setStatus("Не удалось получить ответ.");
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  const builder = (
    <div className="agent-builder">
      <header className="agent-builder-head">
        <h3>Кто отвечает</h3>
        <p className="agent-hint">Инструкция + модель = агент. Чат справа только проверяет его.</p>
      </header>
      <label className="agent-field">
        <span>Имя</span>
        <input
          value={draft.name}
          onChange={(e) => patchDraft({ name: e.target.value })}
          maxLength={120}
        />
      </label>
      <label className="agent-field agent-field--grow">
        <span>Инструкция агента</span>
        <textarea
          value={draft.system_prompt}
          onChange={(e) => patchDraft({ system_prompt: e.target.value })}
          rows={10}
          spellCheck
        />
      </label>
      <fieldset className="agent-how">
        <legend>Как отвечает</legend>
        <p className="agent-hint">Эти настройки живут в агенте, не в обычном чате.</p>
        <label className="agent-field">
          <span>Модель</span>
          <select
            value={draft.preferred_model}
            onChange={(e) => patchDraft({ preferred_model: e.target.value })}
          >
            {modelOptions.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label || m.id}
              </option>
            ))}
          </select>
        </label>
        <label className="agent-field">
          <span>Temperature</span>
          <input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={draft.temperature ?? 0.7}
            onChange={(e) => patchDraft({ temperature: Number(e.target.value) })}
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
            onChange={(e) => patchDraft({ max_tokens: Number(e.target.value) })}
          />
        </label>
      </fieldset>
      <p className="agent-save" aria-live="polite">
        {savedFlash ? "Сохранено · только в этом браузере" : "Черновик · только в этом браузере"}
      </p>
    </div>
  );

  return (
    <section className="agent-workshop" aria-labelledby={titleId}>
      <header className="agent-workshop-top">
        <div className="agent-workshop-title-row">
          <h2 id={titleId}>Агенты</h2>
          <span id={liveId} className="sr-only" aria-live="polite">
            Режим: Агенты
          </span>
          <button
            type="button"
            className="ghost-button agent-mobile-settings"
            onClick={() => setMobileSheet(true)}
          >
            Настройки
          </button>
        </div>
        <div className="agent-library">
          <label className="agent-field agent-field--inline">
            <span className="sr-only">Мои агенты</span>
            <select
              value={draft.id}
              onChange={(e) => switchDraft(e.target.value)}
              aria-label="Мои агенты"
            >
              {store.drafts.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="ghost-button" onClick={newDraft}>
            + Новый агент
          </button>
          <button type="button" className="ghost-button" onClick={renameDraft}>
            Переименовать
          </button>
          <button type="button" className="ghost-button" onClick={deleteDraft}>
            Удалить
          </button>
          <div className="agent-presets" role="group" aria-label="Пресеты">
            {AGENT_PRESETS.map((p, i) => (
              <button
                key={p.name}
                type="button"
                className="chip"
                onClick={() => createFromPreset(i)}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="agent-workshop-body">
        <aside className="agent-workshop-builder desktop-only">{builder}</aside>

        <div className="agent-workshop-dialog">
          <div className="agent-log" aria-live="polite">
            {log.length === 0 ? (
              <div className="agent-log-empty">
                <p>
                  Задай вопрос этому агенту. Каждый вопрос — отдельный прогон; ответ придёт с
                  меткой модели.
                </p>
                <button
                  type="button"
                  className="chip"
                  onClick={() => setInput("Сократи этот текст: ну короче это типа важно")}
                >
                  Пример: сократи текст
                </button>
              </div>
            ) : (
              log.map((line) => (
                <article
                  key={line.id}
                  className={`agent-log-line agent-log-line--${line.role}`}
                >
                  {line.role === "assistant" && line.modelId ? (
                    <span className="badge">{line.modelId}</span>
                  ) : null}
                  <p>{line.text}</p>
                </article>
              ))
            )}
          </div>
          <p className="agent-log-foot">
            Диалог-лог не пишется на сервер (только настройки в браузере). Каждый вопрос —
            отдельный прогон.
          </p>
          {status ? (
            <p className="agent-status" role="status">
              {status}
            </p>
          ) : null}
          <form
            className="agent-compose"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              rows={2}
              placeholder="Сообщение агенту…"
              disabled={busy}
            />
            {busy ? (
              <button type="button" className="agent-send-btn" onClick={stop}>
                Стоп
              </button>
            ) : (
              <button type="submit" className="agent-send-btn" disabled={!input.trim()}>
                Отправить
              </button>
            )}
          </form>
        </div>
      </div>

      {mobileSheet ? (
        <div className="agent-sheet" role="dialog" aria-modal="true" aria-label="Настройки агента">
          <div className="agent-sheet-backdrop" onClick={() => setMobileSheet(false)} />
          <div className="agent-sheet-panel">
            <header className="agent-sheet-head">
              <h3>Настройки</h3>
              <button type="button" className="ghost-button" onClick={() => setMobileSheet(false)}>
                Закрыть
              </button>
            </header>
            {builder}
          </div>
        </div>
      ) : null}
    </section>
  );
}

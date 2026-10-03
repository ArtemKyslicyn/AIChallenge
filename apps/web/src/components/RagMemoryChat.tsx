/** Day 25 — mini-chat: history + always-on RAG sources + task memory. */

import { useEffect, useId, useRef, useState } from "react";

import {
  ApiError,
  clearAgentDialogByDraft,
  getAgentDialogByDraft,
  getAgentMemory,
  postAgentInvariants,
  postAgentTaskEvent,
  runAgentWorkshop,
  type AgentDialogMessageDto,
  type AgentInvariantDto,
  type AgentTaskStateDto,
} from "../api/client";

const DRAFT_ID = "rag-memory-day25";

const DEFINITION = {
  name: "База + память",
  system_prompt: [
    "Ты ассистент стенда AIChallenge с доступом к базе знаний (RAG).",
    "Отвечай по найденным фрагментам и памяти задачи (цель, факты, ограничения).",
    "Если в базе нет ответа — скажи об этом. Не выдумывай порты, токены и имена файлов.",
    "В конце ответа кратко назови title/source использованных фрагментов.",
    "Всегда учитывай цель диалога и зафиксированные ограничения.",
  ].join(" "),
  preferred_model: "auto",
  temperature: 0.3,
  max_tokens: 900,
};

const DEFAULT_GOAL =
  "Разобрать продукт стенда по базе знаний: архитектура, деплой, Guest MCP, model_id.";

type RagSource = {
  chunk_id: string;
  source: string;
  title: string;
  section: string;
  strategy: string;
  score: number;
};

type TurnView = {
  id: string;
  role: "user" | "assistant";
  content: string;
  model_id?: string | null;
  ragSources?: RagSource[];
  ragQueryRewritten?: string | null;
  ragRetrieval?: Record<string, unknown> | null;
};

function mapMessages(
  messages: AgentDialogMessageDto[],
  lastSources?: {
    sources: RagSource[];
    rewritten?: string | null;
    retrieval?: Record<string, unknown> | null;
  },
): TurnView[] {
  const out: TurnView[] = [];
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    const role = m.role === "assistant" ? "assistant" : "user";
    const isLastAssistant =
      role === "assistant" && i === messages.length - 1 && lastSources;
    out.push({
      id: m.id,
      role,
      content: m.content,
      model_id: m.model_id,
      ragSources: isLastAssistant ? lastSources.sources : undefined,
      ragQueryRewritten: isLastAssistant ? lastSources.rewritten : undefined,
      ragRetrieval: isLastAssistant ? lastSources.retrieval : undefined,
    });
  }
  return out;
}

export function RagMemoryChat() {
  const titleId = useId();
  const listRef = useRef<HTMLDivElement>(null);
  const [turns, setTurns] = useState<TurnView[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [task, setTask] = useState<AgentTaskStateDto | null>(null);
  const [facts, setFacts] = useState<Record<string, string>>({});
  const [invariants, setInvariants] = useState<AgentInvariantDto[]>([]);
  const [bootHint, setBootHint] = useState("Готовим диалог…");

  const refreshMemory = async () => {
    const snap = await getAgentMemory(DRAFT_ID);
    setGoal(snap.working?.goal || DEFAULT_GOAL);
    setTask(snap.working?.task ?? null);
    const dialog = await getAgentDialogByDraft(DRAFT_ID);
    if (dialog) {
      setFacts(dialog.facts || {});
      setInvariants(dialog.invariants || []);
      setTurns((prev) => {
        // Keep per-turn sources already attached; refresh text/history.
        const byId = new Map(prev.map((t) => [t.id, t]));
        return (dialog.messages || []).map((m) => {
          const role = m.role === "assistant" ? "assistant" : "user";
          const prevTurn = byId.get(m.id);
          return {
            id: m.id,
            role: role as "user" | "assistant",
            content: m.content,
            model_id: m.model_id,
            ragSources: prevTurn?.ragSources,
            ragQueryRewritten: prevTurn?.ragQueryRewritten,
            ragRetrieval: prevTurn?.ragRetrieval,
          };
        });
      });
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setBootHint("Ставим цель задачи…");
        await postAgentTaskEvent({
          event: "start",
          clientDraftId: DRAFT_ID,
          goal: DEFAULT_GOAL,
          step: "собрать факты из базы",
          expectedAction: "отвечать с источниками RAG",
          dialogName: DEFINITION.name,
          dialogSystemPrompt: DEFINITION.system_prompt,
        });
        setBootHint("Фиксируем ограничения…");
        await postAgentInvariants({
          event: "add",
          clientDraftId: DRAFT_ID,
          kind: "architecture",
          statement: "Не выдумывать порты и путь :443 — только из базы / deploy docs.",
          triggers: [":443", "порт", "xray", "nginx"],
          dialogName: DEFINITION.name,
          dialogSystemPrompt: DEFINITION.system_prompt,
        });
        await postAgentInvariants({
          event: "add",
          clientDraftId: DRAFT_ID,
          kind: "decision",
          statement: "Guest MCP ≠ стендовый /mcp/*.",
          triggers: ["Guest MCP", "guest mcp", "/mcp"],
          dialogName: DEFINITION.name,
          dialogSystemPrompt: DEFINITION.system_prompt,
        });
        if (!cancelled) {
          await refreshMemory();
          setBootHint("");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : String(err));
          setBootHint("");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- boot once per mount
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy]);

  const send = async () => {
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true);
    setError("");
    setText("");
    const optimistic: TurnView = {
      id: `local-${Date.now()}`,
      role: "user",
      content: message,
    };
    setTurns((prev) => [...prev, optimistic]);
    try {
      const result = await runAgentWorkshop(DEFINITION, message, {
        persist: true,
        clientDraftId: DRAFT_ID,
        contextMode: "facts",
        useRag: true,
        ragMode: "full",
        ragTopK: 6,
        includeWorkingMemory: true,
        includeLongTermMemory: true,
      });
      const sources = (result.rag_sources || []).map((s) => ({
        chunk_id: s.chunk_id,
        source: s.source,
        title: s.title,
        section: s.section,
        strategy: s.strategy,
        score: Number(s.score) || 0,
      }));
      if (result.messages?.length) {
        setTurns(
          mapMessages(result.messages, {
            sources,
            rewritten: result.rag_query_rewritten,
            retrieval: result.rag_retrieval ?? null,
          }),
        );
      } else {
        setTurns((prev) => [
          ...prev.filter((t) => t.id !== optimistic.id),
          optimistic,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            content: result.content,
            model_id: result.model_id,
            ragSources: sources,
            ragQueryRewritten: result.rag_query_rewritten,
            ragRetrieval: result.rag_retrieval ?? null,
          },
        ]);
      }
      if (result.invariants) setInvariants(result.invariants);
      if (result.context_strategy?.facts) {
        setFacts(result.context_strategy.facts);
      }
      await refreshMemory();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setTurns((prev) => prev.filter((t) => t.id !== optimistic.id));
      setText(message);
    } finally {
      setBusy(false);
    }
  };

  const onReset = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await clearAgentDialogByDraft(DRAFT_ID);
      setTurns([]);
      setFacts({});
      setInvariants([]);
      await postAgentTaskEvent({
        event: "start",
        clientDraftId: DRAFT_ID,
        goal: DEFAULT_GOAL,
        step: "собрать факты из базы",
        expectedAction: "отвечать с источниками RAG",
        dialogName: DEFINITION.name,
        dialogSystemPrompt: DEFINITION.system_prompt,
      });
      await postAgentInvariants({
        event: "add",
        clientDraftId: DRAFT_ID,
        kind: "architecture",
        statement: "Не выдумывать порты и путь :443 — только из базы / deploy docs.",
        triggers: [":443", "порт", "xray", "nginx"],
        dialogName: DEFINITION.name,
        dialogSystemPrompt: DEFINITION.system_prompt,
      });
      await refreshMemory();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rag-memory-board" aria-labelledby={titleId}>
      <header className="rag-memory-top">
        <div>
          <h2 id={titleId}>База + память</h2>
          <p className="rag-memory-sub">
            Мини-чат: история, always-on RAG со источниками, цель задачи и ограничения.
          </p>
        </div>
        <button
          type="button"
          className="ghost-button"
          disabled={busy}
          onClick={() => void onReset()}
        >
          Новый сценарий
        </button>
      </header>

      <div className="rag-memory-layout">
        <aside className="rag-memory-side" aria-label="Память задачи">
          <section>
            <h3>Цель</h3>
            <p>{goal || "—"}</p>
            {task?.stage ? (
              <p className="rag-memory-meta">
                этап {task.stage}
                {task.step ? ` · ${task.step}` : ""}
              </p>
            ) : null}
          </section>
          <section>
            <h3>Уточнения (facts)</h3>
            {Object.keys(facts).length === 0 ? (
              <p className="rag-memory-meta">Появятся по ходу диалога.</p>
            ) : (
              <ul>
                {Object.entries(facts).map(([k, v]) => (
                  <li key={k}>
                    <strong>{k}</strong>: {v}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section>
            <h3>Ограничения</h3>
            {invariants.length === 0 ? (
              <p className="rag-memory-meta">Пока пусто.</p>
            ) : (
              <ul>
                {invariants
                  .filter((i) => i.active !== false)
                  .map((inv) => (
                    <li key={inv.id}>{inv.statement}</li>
                  ))}
              </ul>
            )}
          </section>
        </aside>

        <div className="rag-memory-main">
          {bootHint ? <p className="center-state">{bootHint}</p> : null}
          {error ? (
            <p className="alert" role="alert">
              {error}
            </p>
          ) : null}
          <div className="rag-memory-log" ref={listRef}>
            {turns.length === 0 && !bootHint ? (
              <p className="rag-memory-meta">
                Задайте вопрос по стенду — ответ опирается на базу и держит цель.
              </p>
            ) : null}
            {turns.map((turn) => (
              <article
                key={turn.id}
                className={`rag-memory-turn rag-memory-turn--${turn.role}`}
              >
                <header>
                  <span>{turn.role === "user" ? "Вы" : "Ассистент"}</span>
                  {turn.model_id ? (
                    <span className="badge" title="model_id">
                      {turn.model_id}
                    </span>
                  ) : null}
                </header>
                <div className="rag-memory-body">{turn.content}</div>
                {turn.role === "assistant" && (
                  <details className="rag-sources" open={Boolean(turn.ragSources?.length)}>
                    <summary>
                      Источники базы · {turn.ragSources?.length ?? 0}
                      {turn.ragRetrieval?.hits_pre != null
                        ? ` (было ${String(turn.ragRetrieval.hits_pre)} → ${String(
                            turn.ragRetrieval.hits_post ?? turn.ragSources?.length ?? 0,
                          )})`
                        : ""}
                      {turn.ragRetrieval?.mode
                        ? ` · ${String(turn.ragRetrieval.mode)}`
                        : ""}
                    </summary>
                    {turn.ragQueryRewritten ? (
                      <p className="rag-sources-rewrite">
                        Запрос после rewrite: {turn.ragQueryRewritten}
                      </p>
                    ) : null}
                    {turn.ragSources && turn.ragSources.length > 0 ? (
                      <ul>
                        {turn.ragSources.map((s) => (
                          <li key={s.chunk_id || `${s.source}-${s.score}`}>
                            <strong>{s.title || s.source}</strong>
                            {s.section ? ` · ${s.section}` : ""}
                            <span className="rag-sources-meta">
                              {" "}
                              ({s.source} · {s.chunk_id} · {s.score.toFixed(2)})
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="rag-memory-meta">Фрагменты не найдены — ответ без цитат.</p>
                    )}
                  </details>
                )}
              </article>
            ))}
            {busy ? (
              <p className="center-state">
                <span className="spinner" aria-hidden="true" /> Ищем в базе и отвечаем…
              </p>
            ) : null}
          </div>

          <form
            className="rag-memory-compose"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <label className="sr-only" htmlFor="rag-memory-input">
              Сообщение
            </label>
            <textarea
              id="rag-memory-input"
              rows={3}
              value={text}
              disabled={busy}
              placeholder="Например: Куда ходит публичный :443? Держись цели и базы."
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <button type="submit" className="primary-button" disabled={busy || !text.trim()}>
              Отправить
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

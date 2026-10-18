/** Stand Copilot — useful assistant skills (days 31–35 under the hood). */

import { useCallback, useEffect, useState } from "react";

import {
  getLocalLlmSource,
  listModels,
  LOCAL_LLM_CHANGED,
  type LocalLlmSourceDto,
  type ModelCatalogItemDto,
} from "../../api/client";
import { loadGlobalChatPrefs, saveGlobalChatPrefs } from "../../chatPrefs";

export type AssistSub =
  | "help"
  | "review"
  | "support"
  | "files"
  | "task";

const STORAGE_KEY = "aichallenge.assist_sub";
const ASSIST_MODEL_KEY = "aichallenge.assist_model";
export const COMPOSER_DRAFT_KEY = "aichallenge.composer_draft";

type Action = {
  id: AssistSub;
  label: string;
  title: string;
  why: string;
  placeholder: string;
};

const ACTIONS: Action[] = [
  {
    id: "help",
    label: "По docs",
    title: "Спросить по документации",
    why: "Ответ только из живых docs стенда, с цитатами — без выдумок.",
    placeholder: "Куда ходит публичный :443 на этом стенде?",
  },
  {
    id: "review",
    label: "Diff",
    title: "Проверить diff",
    why: "Инварианты репо: секреты, deploy-safety, слои. Без обязательного LLM.",
    placeholder: "Проверь последний коммит на секреты и compose down",
  },
  {
    id: "support",
    label: "Разблок",
    title: "Разблокировать меня",
    why: "FAQ + контекст сессии. Если уверенности мало — эскалация, не фантазия.",
    placeholder: "Почему не работает авторизация?",
  },
  {
    id: "files",
    label: "Файлы",
    title: "Работать с файлами на Mac",
    why: "Цель → tools на диске через Guest MCP / aichallenge-mcp-kit.",
    placeholder: "Найди все места с GuestMcp и кратко опиши",
  },
  {
    id: "task",
    label: "Changelog",
    title: "Подготовить changelog",
    why: "Ревью fixture-диффа → AI changelog. В ответе всегда виден model_id.",
    placeholder:
      "Подготовить changelog релиза ассистентов (дни 31–34) по findings инвариант-ревью.",
  },
];

function readSub(): AssistSub {
  if (typeof window === "undefined") return "help";
  try {
    const hash = window.location.hash.replace(/^#/, "");
    if (hash.startsWith("assist/")) {
      const part = hash.slice("assist/".length) as AssistSub;
      if (ACTIONS.some((s) => s.id === part)) return part;
    }
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw && ACTIONS.some((s) => s.id === raw)) return raw as AssistSub;
  } catch {
    /* ignore */
  }
  return "help";
}

function writeSub(sub: AssistSub) {
  try {
    sessionStorage.setItem(STORAGE_KEY, sub);
    const next = `#assist/${sub}`;
    if (window.location.hash !== next) {
      window.history.replaceState(
        {},
        "",
        `${window.location.pathname}${window.location.search}${next}`,
      );
    }
  } catch {
    /* ignore */
  }
}

function readStoredModel(): string | null {
  try {
    return sessionStorage.getItem(ASSIST_MODEL_KEY);
  } catch {
    return null;
  }
}

function writeStoredModel(model: string) {
  try {
    sessionStorage.setItem(ASSIST_MODEL_KEY, model);
  } catch {
    /* ignore */
  }
}

/** Default = first connected ollama/…; else auto. Honor a prior assist pick if still listed. */
function pickDefaultModel(
  catalog: ModelCatalogItemDto[],
  source: LocalLlmSourceDto | null,
  prior: string | null,
): string {
  const ids = new Set(catalog.map((m) => m.id));
  if (prior && (prior === "auto" || ids.has(prior))) return prior;
  const localFromSource = (source?.models ?? [])
    .map((tag) => (tag.startsWith("ollama/") ? tag : `ollama/${tag}`))
    .filter((id) => ids.has(id) || Boolean(source?.enabled));
  if (localFromSource[0]) return localFromSource[0];
  const localFromCatalog = catalog.find((m) => m.id.startsWith("ollama/"));
  if (localFromCatalog) return localFromCatalog.id;
  return "auto";
}

function applyComposerPin(modelId: string) {
  const global = loadGlobalChatPrefs();
  saveGlobalChatPrefs({ ...global, modelId });
  writeStoredModel(modelId);
}

type Props = {
  onOpenMcp?: () => void;
  onOpenChat?: () => void;
};

export function AssistantsPanel({ onOpenMcp, onOpenChat }: Props) {
  const [sub, setSub] = useState<AssistSub>(() => readSub());
  const [goal, setGoal] = useState(() => ACTIONS[0].placeholder);
  const [models, setModels] = useState<ModelCatalogItemDto[]>([]);
  const [source, setSource] = useState<LocalLlmSourceDto | null>(null);
  const [modelId, setModelId] = useState<string>(() => readStoredModel() || "auto");
  const [modelsReady, setModelsReady] = useState(false);

  const refreshModels = useCallback(() => {
    void Promise.all([listModels().catch(() => [] as ModelCatalogItemDto[]), getLocalLlmSource().catch(() => null)]).then(
      ([catalog, src]) => {
        setModels(catalog);
        setSource(src);
        setModelId((prev) => {
          const next = pickDefaultModel(catalog, src, prev === "auto" ? readStoredModel() : prev);
          writeStoredModel(next);
          return next;
        });
        setModelsReady(true);
      },
    );
  }, []);

  useEffect(() => {
    refreshModels();
    const onChange = () => refreshModels();
    window.addEventListener(LOCAL_LLM_CHANGED, onChange);
    return () => window.removeEventListener(LOCAL_LLM_CHANGED, onChange);
  }, [refreshModels]);

  const select = useCallback((next: AssistSub) => {
    setSub(next);
    writeSub(next);
    const action = ACTIONS.find((a) => a.id === next);
    if (action) setGoal(action.placeholder);
  }, []);

  useEffect(() => {
    writeSub(sub);
  }, [sub]);

  const onModelChange = (next: string) => {
    setModelId(next);
    writeStoredModel(next);
  };

  const current = ACTIONS.find((s) => s.id === sub) ?? ACTIONS[0];
  const needsLlm = sub === "help" || sub === "files" || sub === "task";
  const localConnected = Boolean(source?.enabled && source.status === "connected" && source.models.length);

  return (
    <section className="assistants" aria-label="Ассистент стенда">
      <header className="assistants-hero">
        <p className="assistants-kicker">Ассистент стенда</p>
        <h2>Что нужно сделать?</h2>
        <p>
          Один помощник по этому проекту. LLM-навыки по умолчанию с твоего Ollama —
          можно выбрать облако.
        </p>
      </header>

      <div className="assistants-actions" role="tablist" aria-label="Навыки ассистента">
        {ACTIONS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            data-assist-skill={item.id}
            className={
              sub === item.id
                ? "assistants-action assistants-action--on"
                : "assistants-action"
            }
            aria-selected={sub === item.id}
            onClick={() => select(item.id)}
          >
            <span className="assistants-action-label">{item.label}</span>
            <span className="assistants-action-title">{item.title}</span>
          </button>
        ))}
      </div>

      <div className="assistants-panel" role="tabpanel" aria-label={current.title}>
        <div className="assistants-panel-head">
          <h3>{current.title}</h3>
          <p className="assistants-blurb">{current.why}</p>
        </div>

        {needsLlm ? (
          <div className="assistants-model-row">
            <label className="assistants-field">
              Модель
              <select
                data-assist-model
                value={modelId}
                disabled={!modelsReady}
                onChange={(e) => onModelChange(e.target.value)}
              >
                <option value="auto">Авто (цепь стенда)</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.id.startsWith("ollama/") ? `локально · ${m.label || m.id}` : m.label || m.id}
                  </option>
                ))}
              </select>
            </label>
            <p className="assistants-model-hint" data-assist-local={localConnected ? "1" : "0"}>
              {localConnected
                ? modelId.startsWith("ollama/")
                  ? "По умолчанию локальная · можно сменить."
                  : "Выбрано облако / авто · локальная доступна в списке."
                : "Local LLM не подключён — Профиль → Подключения, или работайте через Авто/облако."}
            </p>
          </div>
        ) : null}

        <label className="assistants-field">
          Цель
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            rows={3}
            data-assist-goal
          />
        </label>

        {sub === "help" ? (
          <HelpPane goal={goal} modelId={modelId} onOpenChat={onOpenChat} />
        ) : sub === "review" ? (
          <ReviewPane goal={goal} />
        ) : sub === "support" ? (
          <SupportPane goal={goal} />
        ) : sub === "files" ? (
          <FilesPane goal={goal} modelId={modelId} onOpenMcp={onOpenMcp} onOpenChat={onOpenChat} />
        ) : (
          <TaskPane goal={goal} modelId={modelId} />
        )}
      </div>

      <details className="assistants-course">
        <summary>Для сдачи курса (дни 31–35)</summary>
        <ul>
          <li>
            <code>challenges/31-dev-help/</code> — По docs (рекомендуется бейдж <code>ollama/…</code>)
          </li>
          <li>
            <code>challenges/32-pr-review/</code> — Diff (без LLM)
          </li>
          <li>
            <code>challenges/33-support-desk/</code> — Разблок (FAQ, не LLM)
          </li>
          <li>
            <code>challenges/34-file-assistant/</code> — Файлы
          </li>
          <li>
            <code>challenges/35-real-task/</code> — Changelog (рекомендуется <code>ollama/…</code>)
          </li>
        </ul>
      </details>
    </section>
  );
}

function HelpPane({
  goal,
  modelId,
  onOpenChat,
}: {
  goal: string;
  modelId: string;
  onOpenChat?: () => void;
}) {
  const run = () => {
    applyComposerPin(modelId);
    const q = goal.trim() || "куда ходит публичный :443?";
    const draft = q.startsWith("/help") || q.startsWith("/помощь") ? q : `/help ${q}`;
    try {
      sessionStorage.setItem(COMPOSER_DRAFT_KEY, draft);
    } catch {
      /* ignore */
    }
    onOpenChat?.();
  };

  return (
    <div className="assistants-body">
      <ol className="assistants-steps">
        <li>Сформулируйте вопрос по стенду (деплой, :443, RAG, MCP…).</li>
        <li>
          Нажмите «Спросить в чате» — уйдёт <code>/help</code> с выбранной моделью.
        </li>
        <li>В ответе: цитаты / источники и бейдж model_id.</li>
      </ol>
      <button type="button" className="primary-button" data-assist-action="help" onClick={run}>
        Спросить в чате
      </button>
      <p className="assistants-done">
        Готово, когда ответ опирается на handbook и есть источники (или честное «нет в базе»).
        Для сдачи курса предпочтителен бейдж <code>ollama/…</code>.
      </p>
    </div>
  );
}

function ReviewPane({ goal }: { goal: string }) {
  return (
    <div className="assistants-body">
      <ol className="assistants-steps">
        <li>Цель: {goal.trim() || "проверить diff на секреты и deploy-safety"}.</li>
        <li>Локально или в CI прогоните инвариант-ревью (без LLM):</li>
      </ol>
      <pre className="assistants-code">{`python3 challenges/32-pr-review/run.py
./scripts/review.sh HEAD~1`}</pre>
      <p className="assistants-done">
        Готово, когда отчёт показывает findings (секреты → fail) или чистый проход. Workflow:{" "}
        <code>.github/workflows/review.yml</code>
      </p>
    </div>
  );
}

function SupportPane({ goal }: { goal: string }) {
  const [question, setQuestion] = useState(goal);
  const [ticketId, setTicketId] = useState("demo-auth-1");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setQuestion(goal);
  }, [goal]);

  const ask = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/v1/support/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim() || goal,
          ticket_id: ticketId || null,
          session_snapshot: { shell: "assist", panel: "support" },
        }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = (await res.json()) as {
        body: string;
        escalate: boolean;
        model_id: string;
      };
      setResult(
        `${data.body}\n\n— model_id: ${data.model_id}${data.escalate ? " · escalate" : ""}`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="assistants-body">
      <ol className="assistants-steps">
        <li>Опишите, где застряли (можно ticket_id из FAQ).</li>
        <li>Ответ из FAQ + снимка сессии — без генерации LLM.</li>
        <li>
          <code>model_id: support-faq</code> — метка FAQ, не модель чата.
        </li>
      </ol>
      <label className="assistants-field">
        ticket_id
        <input value={ticketId} onChange={(e) => setTicketId(e.target.value)} />
      </label>
      <button
        type="button"
        className="primary-button"
        data-assist-action="support"
        disabled={busy}
        onClick={() => void ask()}
      >
        {busy ? "Спрашиваю…" : "Разблокировать"}
      </button>
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      {result ? (
        <pre className="assistants-code" data-assist-result="support">
          {result}
        </pre>
      ) : null}
      <p className="assistants-done">
        Готово, когда есть ответ (и escalate, если базы не хватило).
      </p>
    </div>
  );
}

function FilesPane({
  goal,
  modelId,
  onOpenMcp,
  onOpenChat,
}: {
  goal: string;
  modelId: string;
  onOpenMcp?: () => void;
  onOpenChat?: () => void;
}) {
  const openChatWithGoal = () => {
    applyComposerPin(modelId);
    try {
      sessionStorage.setItem(COMPOSER_DRAFT_KEY, goal.trim() || "Найди все места с GuestMcp");
    } catch {
      /* ignore */
    }
    onOpenChat?.();
  };

  return (
    <div className="assistants-body">
      <ol className="assistants-steps">
        <li>
          Цель на уровне задачи: <em>{goal.trim() || "найди usages / обнови README"}</em>.
        </li>
        <li>
          Запустите <code>aichallenge-mcp-kit</code> и туннель.
        </li>
        <li>Профиль → Свой MCP → URL + token.</li>
        <li>В чате отправьте цель — ассистент вызовет file tools (модель из селектора).</li>
      </ol>
      <div className="assistants-btn-row">
        {onOpenMcp ? (
          <button
            type="button"
            className="primary-button"
            data-assist-action="files"
            onClick={onOpenMcp}
          >
            Открыть MCP
          </button>
        ) : null}
        {onOpenChat ? (
          <button type="button" className="ghost-button" onClick={openChatWithGoal}>
            В чат с целью
          </button>
        ) : null}
      </div>
      <p className="assistants-done">
        Готово, когда в логе видны tool-вызовы (search/read/write) и diff по цели.
      </p>
    </div>
  );
}

function TaskPane({ goal, modelId }: { goal: string; modelId: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<{
    steps: string[];
    review_markdown: string;
    changelog: string;
    model_id: string;
  } | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    setPayload(null);
    try {
      const res = await fetch("/api/v1/assistants/real-task", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: goal.trim() || null,
          model: modelId || "auto",
        }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = (await res.json()) as {
        steps: string[];
        review_markdown: string;
        changelog: string;
        model_id: string;
      };
      setPayload(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="assistants-body">
      <ol className="assistants-steps">
        <li>Сначала инвариант-ревью (без LLM), потом changelog выбранной моделью.</li>
        <li>
          По умолчанию локальная; в ответе обязателен <code>model_id</code>.
        </li>
      </ol>
      <button
        type="button"
        className="primary-button"
        data-assist-action="real-task"
        disabled={busy}
        onClick={() => void run()}
      >
        {busy ? "Готовлю changelog…" : "Подготовить changelog"}
      </button>
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      {payload ? (
        <div className="assistants-task-result" data-assist-result="real-task">
          <p>
            <strong>model_id:</strong> <code>{payload.model_id}</code>
          </p>
          <ol>
            {payload.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          <h4>Ревью</h4>
          <pre className="assistants-code">{payload.review_markdown}</pre>
          <h4>Changelog</h4>
          <pre className="assistants-code">{payload.changelog}</pre>
        </div>
      ) : null}
      <p className="assistants-done">
        Готово, когда на экране model_id + changelog. Для сдачи — <code>ollama/…</code>.
      </p>
    </div>
  );
}

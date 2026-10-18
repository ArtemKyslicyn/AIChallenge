/** Stand Copilot — useful assistant skills (days 31–35 under the hood). */

import { useCallback, useEffect, useState } from "react";

export type AssistSub =
  | "help"
  | "review"
  | "support"
  | "files"
  | "task";

const STORAGE_KEY = "aichallenge.assist_sub";
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

type Props = {
  onOpenMcp?: () => void;
  onOpenChat?: () => void;
};

export function AssistantsPanel({ onOpenMcp, onOpenChat }: Props) {
  const [sub, setSub] = useState<AssistSub>(() => readSub());
  const [goal, setGoal] = useState(() => ACTIONS[0].placeholder);

  const select = useCallback((next: AssistSub) => {
    setSub(next);
    writeSub(next);
    const action = ACTIONS.find((a) => a.id === next);
    if (action) setGoal(action.placeholder);
  }, []);

  useEffect(() => {
    writeSub(sub);
  }, [sub]);

  const current = ACTIONS.find((s) => s.id === sub) ?? ACTIONS[0];

  return (
    <section className="assistants" aria-label="Ассистент стенда">
      <header className="assistants-hero">
        <p className="assistants-kicker">Ассистент стенда</p>
        <h2>Что нужно сделать?</h2>
        <p>
          Один помощник по этому проекту: docs, проверка diff, разблокировка,
          файлы на Mac и changelog релиза. Не лабораторка — рабочие навыки.
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
          <HelpPane goal={goal} onOpenChat={onOpenChat} />
        ) : sub === "review" ? (
          <ReviewPane goal={goal} />
        ) : sub === "support" ? (
          <SupportPane goal={goal} />
        ) : sub === "files" ? (
          <FilesPane goal={goal} onOpenMcp={onOpenMcp} />
        ) : (
          <TaskPane goal={goal} />
        )}
      </div>

      <details className="assistants-course">
        <summary>Для сдачи курса (дни 31–35)</summary>
        <ul>
          <li>
            <code>challenges/31-dev-help/</code> — По docs
          </li>
          <li>
            <code>challenges/32-pr-review/</code> — Diff
          </li>
          <li>
            <code>challenges/33-support-desk/</code> — Разблок
          </li>
          <li>
            <code>challenges/34-file-assistant/</code> — Файлы
          </li>
          <li>
            <code>challenges/35-real-task/</code> — Changelog
          </li>
        </ul>
      </details>
    </section>
  );
}

function HelpPane({
  goal,
  onOpenChat,
}: {
  goal: string;
  onOpenChat?: () => void;
}) {
  const run = () => {
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
          Нажмите «Спросить в чате» — уйдёт запрос с <code>/help</code>.
        </li>
        <li>В ответе смотрите цитаты / «Источники базы» и бейдж model_id.</li>
      </ol>
      <button type="button" className="primary-button" data-assist-action="help" onClick={run}>
        Спросить в чате
      </button>
      <p className="assistants-done">
        Готово, когда ответ опирается на handbook и есть источники (или честное «нет в базе»).
      </p>
    </div>
  );
}

function ReviewPane({ goal }: { goal: string }) {
  return (
    <div className="assistants-body">
      <ol className="assistants-steps">
        <li>Цель: {goal.trim() || "проверить diff на секреты и deploy-safety"}.</li>
        <li>Локально или в CI прогоните инвариант-ревью:</li>
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
        <li>Ассистент ответит по FAQ + снимку сессии.</li>
        <li>При слабом hit увидите escalate — так и должно быть.</li>
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
        Готово, когда есть ответ с model_id (и escalate, если базы не хватило).
      </p>
    </div>
  );
}

function FilesPane({
  goal,
  onOpenMcp,
}: {
  goal: string;
  onOpenMcp?: () => void;
}) {
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
        <li>В чате отправьте цель — ассистент вызовет file tools на Mac.</li>
      </ol>
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
      <p className="assistants-done">
        Готово, когда в логе видны tool-вызовы (search/read/write) и diff по цели.
      </p>
    </div>
  );
}

function TaskPane({ goal }: { goal: string }) {
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
        body: JSON.stringify({ goal: goal.trim() || null }),
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
        <li>Запустите задачу на стенде — сначала инвариант-ревью, потом LLM.</li>
        <li>В результате обязателен <code>model_id</code> и текст changelog.</li>
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
        Готово, когда на экране model_id + changelog по findings ревью.
      </p>
    </div>
  );
}

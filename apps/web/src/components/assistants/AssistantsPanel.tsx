/** Days 31–35 — product Assistants feature (topbar tab). */

import { useCallback, useEffect, useState } from "react";

export type AssistSub =
  | "help"
  | "review"
  | "support"
  | "files"
  | "task";

const STORAGE_KEY = "aichallenge.assist_sub";

const SUBS: { id: AssistSub; label: string; blurb: string }[] = [
  {
    id: "help",
    label: "Справка",
    blurb: "Ответы только из handbook-корпуса с цитатами и контекстом сборки.",
  },
  {
    id: "review",
    label: "Ревью",
    blurb: "Проверка диффа по инвариантам репо (секреты, deploy-safety, слои). CI + локальный CLI.",
  },
  {
    id: "support",
    label: "Поддержка",
    blurb: "FAQ + снимок вашей сессии + тикет. При слабой уверенности — эскалация.",
  },
  {
    id: "files",
    label: "Файлы",
    blurb: "Цель → tools на вашем Mac через Guest MCP / aichallenge-mcp-kit.",
  },
  {
    id: "task",
    label: "Задача",
    blurb:
      "Реальный пайплайн на стенде: инвариант-ревью → AI changelog (model_id). Опционально тот же сценарий в Agent07.",
  },
];

function readSub(): AssistSub {
  if (typeof window === "undefined") return "help";
  try {
    const hash = window.location.hash.replace(/^#/, "");
    if (hash.startsWith("assist/")) {
      const part = hash.slice("assist/".length) as AssistSub;
      if (SUBS.some((s) => s.id === part)) return part;
    }
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw && SUBS.some((s) => s.id === raw)) return raw as AssistSub;
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
      window.history.replaceState({}, "", `${window.location.pathname}${window.location.search}${next}`);
    }
  } catch {
    /* ignore */
  }
}

type Props = {
  onOpenMcp?: () => void;
};

export function AssistantsPanel({ onOpenMcp }: Props) {
  const [sub, setSub] = useState<AssistSub>(() => readSub());

  const select = useCallback((next: AssistSub) => {
    setSub(next);
    writeSub(next);
  }, []);

  useEffect(() => {
    writeSub(sub);
  }, [sub]);

  const current = SUBS.find((s) => s.id === sub) ?? SUBS[0];

  return (
    <section className="assistants" aria-label="Ассистенты">
      <header className="assistants-hero">
        <h2>Ассистенты</h2>
        <p>
          Справка, ревью, поддержка, файлы и реальная задача — один раздел стенда.
          Desktop-продукт: Agent07; мост к диску: aichallenge-mcp-kit.
        </p>
      </header>

      <nav className="assistants-subnav" role="tablist" aria-label="Режимы ассистентов">
        {SUBS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            className={
              sub === item.id
                ? "assistants-subnav-btn assistants-subnav-btn--on"
                : "assistants-subnav-btn"
            }
            aria-selected={sub === item.id}
            onClick={() => select(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="assistants-panel" role="tabpanel" aria-label={current.label}>
        <h3>{current.label}</h3>
        <p className="assistants-blurb">{current.blurb}</p>

        {sub === "help" ? (
          <HelpPane />
        ) : sub === "review" ? (
          <ReviewPane />
        ) : sub === "support" ? (
          <SupportPane />
        ) : sub === "files" ? (
          <FilesPane onOpenMcp={onOpenMcp} />
        ) : (
          <TaskPane />
        )}
      </div>
    </section>
  );
}

function HelpPane() {
  return (
    <div className="assistants-body">
      <p>
        Задайте цель в чате с префиксом <code>/help</code> или откройте вопрос здесь после
        подключения handbook RAG. Ответ только по живым docs + цитаты; нет хита — «нет в базе».
      </p>
      <ul>
        <li>
          Корпус: <code>docs/*.md</code>, README, AGENTS — без планов{" "}
          <code>docs/superpowers/</code>
        </li>
        <li>
          Пример: <code>/help куда ходит :443?</code>
        </li>
      </ul>
      <p className="assistants-hint">
        Challenge: <code>challenges/31-dev-help/</code>
      </p>
    </div>
  );
}

function ReviewPane() {
  return (
    <div className="assistants-body">
      <p>
        Advisory-ревью по инвариантам репо. Локально и в GitHub Actions — без обязательного
        LLM-ключа. Блокирует только находки секретов.
      </p>
      <pre className="assistants-code">{`python3 challenges/32-pr-review/run.py
# или
./scripts/review.sh HEAD~1`}</pre>
      <p className="assistants-hint">
        Workflow: <code>.github/workflows/review.yml</code> · Challenge:{" "}
        <code>challenges/32-pr-review/</code>
      </p>
    </div>
  );
}

function SupportPane() {
  const [question, setQuestion] = useState("Почему не работает авторизация?");
  const [ticketId, setTicketId] = useState("demo-auth-1");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/v1/support/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
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
      <p>
        FAQ + контекст вашей сессии + опциональный ticket_id. Слабый hit → эскалация, не
        выдуманный workaround.
      </p>
      <label className="assistants-field">
        Вопрос
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
        />
      </label>
      <label className="assistants-field">
        ticket_id
        <input value={ticketId} onChange={(e) => setTicketId(e.target.value)} />
      </label>
      <button type="button" className="ghost-button" disabled={busy} onClick={() => void ask()}>
        {busy ? "Спрашиваю…" : "Спросить поддержку"}
      </button>
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      {result ? <pre className="assistants-code">{result}</pre> : null}
      <p className="assistants-hint">
        Challenge: <code>challenges/33-support-desk/</code>
      </p>
    </div>
  );
}

function FilesPane({ onOpenMcp }: { onOpenMcp?: () => void }) {
  return (
    <div className="assistants-body">
      <p>
        Ассистент сам читает/ищет/пишет файлы в workspace kit через Guest MCP. Цель на уровне
        задачи, не «открой файл X».
      </p>
      <ol>
        <li>
          Запустите <code>aichallenge-mcp-kit</code> и туннель.
        </li>
        <li>Профиль → Свой MCP → URL + token.</li>
        <li>В чате сформулируйте цель (найти usages / обновить README).</li>
      </ol>
      {onOpenMcp ? (
        <button type="button" className="ghost-button" onClick={onOpenMcp}>
          Открыть MCP
        </button>
      ) : null}
      <p className="assistants-hint">
        Challenge: <code>challenges/34-file-assistant/</code>
      </p>
    </div>
  );
}

function TaskPane() {
  const [goal, setGoal] = useState(
    "Подготовить changelog релиза ассистентов (дни 31–34) по findings инвариант-ревью.",
  );
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
        body: JSON.stringify({ goal }),
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
      <p>
        Реальная задача <strong>на этом стенде</strong>: прогон инвариант-ревью → генерация
        changelog через LLM. В ответе виден <code>model_id</code>. Тот же класс задач можно
        закрывать в{" "}
        <a href="https://github.com/ArtemKyslicyn/Agent07" rel="noreferrer" target="_blank">
          Agent07
        </a>
        .
      </p>
      <label className="assistants-field">
        Цель
        <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} />
      </label>
      <button
        type="button"
        className="ghost-button"
        data-assist-action="real-task"
        disabled={busy}
        onClick={() => void run()}
      >
        {busy ? "Выполняю…" : "Запустить задачу"}
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
      <p className="assistants-hint">
        Challenge: <code>challenges/35-real-task/</code> · API{" "}
        <code>POST /api/v1/assistants/real-task</code>
      </p>
    </div>
  );
}

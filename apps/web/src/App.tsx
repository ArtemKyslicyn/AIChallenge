import { useCallback, useEffect, useState } from "react";

import {
  createNewSession,
  ensureSession,
  forgetActiveSession,
  listChatHistory,
  switchSession,
  touchSessionTitle,
  type ChatHistoryItem,
  type SessionCredentials,
} from "./api/client";
import { AgentBattle } from "./components/AgentBattle";
import { McpCatalog } from "./components/McpCatalog";
import { AgentStudio } from "./components/AgentStudio";
import { AgentWorkshop } from "./components/AgentWorkshop";
import { AuthPanel } from "./components/AuthPanel";
import { BenchmarksBoard } from "./components/BenchmarksBoard";
import { Chat } from "./components/Chat";
import { SessionSidebar } from "./components/SessionSidebar";
import { DebugProvider } from "./debug/DebugContext";
import { readShellMode, writeShellMode, type ShellMode } from "./shellMode";

export default function App() {
  const [shellMode, setShellMode] = useState<ShellMode>(() => readShellMode());
  const [session, setSession] = useState<SessionCredentials | null>(null);
  const [history, setHistory] = useState<ChatHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);

  const setMode = useCallback((mode: ShellMode) => {
    writeShellMode(mode);
    setShellMode(mode);
    if (
      mode === "agents" ||
      mode === "graph" ||
      mode === "benchmarks" ||
      mode === "battle" ||
      mode === "mcp"
    ) {
      setSidebarOpen(false);
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      setHistory(await listChatHistory());
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const boot = useCallback(() => {
    setBooting(true);
    setError(null);
    ensureSession()
      .then((next) => {
        setSession(next);
        return refreshHistory();
      })
      .catch((e: Error) => {
        setSession(null);
        if (e.name === "TimeoutError" || e.name === "AbortError") {
          setError(
            "Сервер не отвечает (часто порт 443). Откройте https://aichallenge.arcilite.ru:8443/ или обновите страницу.",
          );
        } else {
          setError(e.message);
        }
      })
      .finally(() => setBooting(false));
  }, [refreshHistory]);

  useEffect(() => {
    boot();
  }, [boot]);

  const openNewChat = useCallback(async () => {
    setError(null);
    setBooting(true);
    try {
      const next = await createNewSession();
      setSession(next);
      await refreshHistory();
      setSidebarOpen(false);
      setMode("chat");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBooting(false);
    }
  }, [refreshHistory, setMode]);

  const pickSession = useCallback(
    async (sessionId: string) => {
      const picked = switchSession(sessionId);
      if (!picked) return;
      setSession({ ...picked });
      setSidebarOpen(false);
      setMode("chat");
      await refreshHistory();
    },
    [refreshHistory, setMode],
  );

  const onStaleSession = useCallback(() => {
    forgetActiveSession();
    setSession(null);
    boot();
  }, [boot]);

  const onFirstMessage = useCallback(
    (text: string) => {
      if (!session) return;
      touchSessionTitle(session.id, text);
      void refreshHistory();
    },
    [session, refreshHistory],
  );

  const inAgents = shellMode === "agents";
  const inGraph = shellMode === "graph";
  const inBenchmarks = shellMode === "benchmarks";
  const inBattle = shellMode === "battle";
  const inMcp = shellMode === "mcp";
  const showChatChrome = shellMode === "chat";
  const shellLabel =
    shellMode === "agents"
      ? "Агенты"
      : shellMode === "graph"
        ? "Схема"
        : shellMode === "benchmarks"
          ? "Замеры"
          : shellMode === "battle"
            ? "Битва"
            : shellMode === "mcp"
              ? "MCP"
              : "Чат";

  return (
    <DebugProvider>
      <div
        className={`app${inAgents ? " app--agents" : ""}${inGraph ? " app--graph" : ""}${inBenchmarks ? " app--benchmarks" : ""}${inBattle ? " app--battle" : ""}${inMcp ? " app--mcp" : ""}`}
      >
        {showChatChrome ? (
          <SessionSidebar
            items={history}
            activeId={session?.id ?? null}
            loading={historyLoading}
            open={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
            onSelect={(id) => void pickSession(id)}
            onNew={() => void openNewChat()}
          />
        ) : null}

        <div className="app-main">
          <header className="topbar">
            <div className="brand">
              {showChatChrome ? (
                <button
                  type="button"
                  className="ghost-button sidebar-toggle"
                  aria-expanded={sidebarOpen}
                  aria-controls="chat-sidebar"
                  onClick={() => setSidebarOpen(true)}
                >
                  История
                </button>
              ) : null}
              <span
                className="dot"
                data-state={
                  inAgents || inGraph || inBenchmarks || inBattle || inMcp || session
                    ? "online"
                    : "offline"
                }
                aria-hidden="true"
              />
              <div className="brand-text">
                <h1>AIChallenge</h1>
                <p className="brand-tagline">Чат, в котором видно модель</p>
              </div>
            </div>

            <nav
              className="shell-mode"
              role="group"
              aria-label="Разделы стенда"
            >
              <button
                type="button"
                className="shell-mode-btn"
                aria-pressed={shellMode === "chat"}
                title="Прозрачный ответ: у каждого сообщения свой model_id"
                onClick={() => setMode("chat")}
              >
                Чат
              </button>
              <button
                type="button"
                className="shell-mode-btn"
                aria-pressed={shellMode === "agents"}
                title="Лаборатория: собрать агента или команду"
                onClick={() => setMode("agents")}
              >
                Агенты
              </button>
              <button
                type="button"
                className="shell-mode-btn"
                aria-pressed={shellMode === "graph"}
                title="Схема агентов: пайплайн узлов одним прогоном"
                onClick={() => setMode("graph")}
              >
                Схема
              </button>
              <button
                type="button"
                className="shell-mode-btn"
                aria-pressed={shellMode === "benchmarks"}
                title="Таблица правды: harness-bench по моделям из цепочки"
                onClick={() => setMode("benchmarks")}
              >
                Замеры
              </button>
              <button
                type="button"
                className="shell-mode-btn"
                aria-pressed={shellMode === "battle"}
                title="Песочница: конкурирующие агенты в вымышленном кризисе"
                onClick={() => setMode("battle")}
              >
                Битва
              </button>
              <button
                type="button"
                className="shell-mode-btn"
                aria-pressed={shellMode === "mcp"}
                title="Дежурство стенда: вахта, инциденты, ночная сводка"
                onClick={() => setMode("mcp")}
              >
                MCP
              </button>
            </nav>

            <AuthPanel />

            <span className="sr-only" aria-live="polite">
              Раздел: {shellLabel}
            </span>
          </header>

          {error && showChatChrome && (
            <p className="alert" role="alert">
              {error}
            </p>
          )}

          {inAgents ? (
            <AgentWorkshop />
          ) : inGraph ? (
            <AgentStudio />
          ) : inBenchmarks ? (
            <BenchmarksBoard />
          ) : inBattle ? (
            <AgentBattle />
          ) : inMcp ? (
            <McpCatalog />
          ) : (
            <>
              {(booting || (!session && !error)) && (
                <p className="center-state">
                  <span className="spinner" aria-hidden="true" /> Создаём сессию…
                </p>
              )}

              {session && !booting && (
                <Chat
                  key={session.id}
                  session={session}
                  onStaleSession={onStaleSession}
                  onFirstMessage={onFirstMessage}
                  onOpenAgents={() => setMode("agents")}
                  onOpenGraph={() => setMode("graph")}
                  onOpenBenchmarks={() => setMode("benchmarks")}
                  onOpenBattle={() => setMode("battle")}
                />
              )}
            </>
          )}
        </div>
      </div>
    </DebugProvider>
  );
}

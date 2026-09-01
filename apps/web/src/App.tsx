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
import { Chat } from "./components/Chat";
import { SessionSidebar } from "./components/SessionSidebar";

export default function App() {
  const [session, setSession] = useState<SessionCredentials | null>(null);
  const [history, setHistory] = useState<ChatHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);

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
        setError(e.message);
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBooting(false);
    }
  }, [refreshHistory]);

  const pickSession = useCallback(
    async (sessionId: string) => {
      const picked = switchSession(sessionId);
      if (!picked) return;
      setSession({ ...picked });
      setSidebarOpen(false);
      await refreshHistory();
    },
    [refreshHistory],
  );

  return (
    <div className="app">
      <SessionSidebar
        items={history}
        activeId={session?.id ?? null}
        loading={historyLoading}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onSelect={(id) => void pickSession(id)}
        onNew={() => void openNewChat()}
      />

      <div className="app-main">
        <header className="topbar">
          <div className="brand">
            <button
              type="button"
              className="ghost-button sidebar-toggle"
              aria-expanded={sidebarOpen}
              aria-controls="chat-sidebar"
              onClick={() => setSidebarOpen(true)}
            >
              История
            </button>
            <span className="dot" data-state={session ? "online" : "offline"} aria-hidden="true" />
            <h1>AI Чат-платформа</h1>
          </div>

          {session && (
            <button
              type="button"
              className="ghost-button"
              onClick={() => void openNewChat()}
            >
              Новый чат
            </button>
          )}
        </header>

        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}

        {(booting || (!session && !error)) && (
          <p className="center-state">
            <span className="spinner" aria-hidden="true" /> Создаём сессию…
          </p>
        )}

        {session && !booting && (
          <Chat
            key={session.id}
            session={session}
            onStaleSession={() => {
              forgetActiveSession();
              setSession(null);
              boot();
            }}
            onFirstMessage={(text) => {
              touchSessionTitle(session.id, text);
              void refreshHistory();
            }}
          />
        )}
      </div>
    </div>
  );
}

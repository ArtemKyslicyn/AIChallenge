import { useEffect, useState } from "react";

import { ensureSession, forgetSession, type SessionCredentials } from "./api/client";
import { Chat } from "./components/Chat";

export default function App() {
  const [session, setSession] = useState<SessionCredentials | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ensureSession()
      .then(setSession)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="dot" data-state={session ? "online" : "offline"} aria-hidden="true" />
          <h1>AI Чат-платформа</h1>
          {session && <span className="session-id">{session.id.slice(0, 8)}</span>}
        </div>

        {session && (
          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              forgetSession();
              window.location.reload();
            }}
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

      {!session && !error && (
        <p className="center-state">
          <span className="spinner" aria-hidden="true" /> Создаём сессию…
        </p>
      )}

      {session && <Chat session={session} />}
    </div>
  );
}

import { useEffect, useState } from "react";

import { ensureSession, forgetSession, type SessionCredentials } from "./api/client";
import { Chat } from "./components/Chat";
import { Probe } from "./components/Probe";

export default function App() {
  const [session, setSession] = useState<SessionCredentials | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ensureSession()
      .then(setSession)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main className="app">
      <header>
        <h1>AI Chat Platform</h1>
        {session && (
          <button
            type="button"
            className="link"
            onClick={() => {
              forgetSession();
              window.location.reload();
            }}
          >
            New session
          </button>
        )}
      </header>

      {error && <p className="error">{error}</p>}
      {!session && !error && <p className="hint">Starting a session…</p>}

      {session && (
        <div className="layout">
          <Chat session={session} />
          <Probe />
        </div>
      )}
    </main>
  );
}

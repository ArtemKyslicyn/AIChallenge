import { useState } from "react";

import { probeComplete, type ProbeResult } from "../api/client";

export function Probe() {
  const [prompt, setPrompt] = useState("Say hello in one short sentence.");
  const [result, setResult] = useState<ProbeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await probeComplete(prompt));
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="probe">
      <h2>Probe</h2>
      <p className="hint">Calls the model directly. Nothing is written to the database.</p>
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={3}
        aria-label="Probe prompt"
      />
      <button type="button" onClick={() => void run()} disabled={busy || !prompt.trim()}>
        {busy ? "Calling…" : "Run probe"}
      </button>

      {error && <p className="error">{error}</p>}
      {result && (
        <div className="probe-result">
          <p className="content">{result.content}</p>
          <p className="meta">model: {result.model_id}</p>
        </div>
      )}
    </aside>
  );
}

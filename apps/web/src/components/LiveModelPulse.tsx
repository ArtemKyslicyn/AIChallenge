import { useCallback, useEffect, useRef, useState } from "react";

import { fetchLiveModelPulse, type LiveModelPulseDto } from "../api/client";

interface Props {
  selectedId: string;
  onPick: (modelId: string) => void;
}

function shortId(id: string): string {
  const tail = id.split("/").pop() || id;
  return tail.length > 22 ? `${tail.slice(0, 20)}…` : tail;
}

export function LiveModelPulse({ selectedId, onPick }: Props) {
  const [pulse, setPulse] = useState<LiveModelPulseDto | null>(null);
  const [busy, setBusy] = useState(false);
  const inflight = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    inflight.current?.abort();
    const ac = new AbortController();
    inflight.current = ac;
    setBusy(true);
    try {
      setPulse(await fetchLiveModelPulse(ac.signal));
    } catch {
      if (ac.signal.aborted) return;
    } finally {
      if (inflight.current === ac) setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => inflight.current?.abort();
  }, [refresh]);

  const leader = (pulse?.ranking ?? []).find((row) => !row.avoid);
  const label = selectedId ? shortId(selectedId) : leader ? shortId(leader.model_id) : "Авто";
  const phase = busy ? "busy" : pulse ? "ready" : "idle";

  return (
    <section
      className="composer-live-pulse"
      aria-label="Сейчас в чат"
      data-phase={phase}
      data-pulse-count={pulse ? "1" : "0"}
    >
      <span className="composer-live-now-kicker">сейчас</span>
      <button
        type="button"
        className="composer-live-chip"
        data-state={selectedId ? "on" : "live"}
        onClick={() => onPick(selectedId || leader?.model_id || "")}
      >
        <code>{label}</code>
      </button>
      <button type="button" className="composer-live-refresh" disabled={busy} onClick={() => void refresh()}>
        {busy ? "…" : "пульс"}
      </button>
    </section>
  );
}

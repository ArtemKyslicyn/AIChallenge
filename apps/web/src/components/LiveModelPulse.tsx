import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchLiveModelPulse,
  type LiveModelPulseDto,
  type LiveModelRow,
} from "../api/client";

interface Props {
  selectedId: string;
  catalogIds: string[];
  onPick: (modelId: string) => void;
}

function shortId(id: string): string {
  const tail = id.split("/").pop() || id;
  return tail.length > 22 ? `${tail.slice(0, 20)}…` : tail;
}

export function LiveModelPulse({ selectedId, catalogIds, onPick }: Props) {
  const [pulse, setPulse] = useState<LiveModelPulseDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inflight = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    inflight.current?.abort();
    const ac = new AbortController();
    inflight.current = ac;
    setBusy(true);
    setError(null);
    try {
      setPulse(await fetchLiveModelPulse(ac.signal));
    } catch (exc) {
      if (ac.signal.aborted) return;
      setError(exc instanceof Error ? exc.message : "пульс недоступен");
    } finally {
      if (inflight.current === ac) setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => inflight.current?.abort();
  }, [refresh]);

  const avoidIds = new Set(pulse?.attention.map((row) => row.model_id) ?? []);
  const live = (pulse?.ranking ?? []).filter((row) => !row.avoid).slice(0, 3);
  const avoid = pulse?.attention.slice(0, 2) ?? [];
  const extras: LiveModelRow[] =
    live.length === 0
      ? catalogIds.filter((id) => id && id !== "auto").slice(0, 3).map((model_id) => ({ model_id, avoid: false }))
      : [];
  const takeRows = live.length ? live : extras;
  const phase = busy ? "busy" : error ? "error" : pulse ? "ready" : "idle";

  return (
    <section
      className="composer-live-pulse"
      aria-label="Живой выбор модели"
      data-phase={phase}
      data-open="0"
      data-pulse-count={pulse ? "1" : "0"}
    >
      <div className="composer-live-chips">
        {takeRows.map((row) => (
          <button
            key={row.model_id}
            type="button"
            className="composer-live-chip"
            data-state={selectedId === row.model_id ? "on" : "live"}
            onClick={() => onPick(row.model_id)}
          >
            <code>{shortId(row.model_id)}</code>
          </button>
        ))}
        {avoid.map((row) => (
          <button
            key={`avoid-${row.model_id}`}
            type="button"
            className="composer-live-chip"
            data-state="avoid"
            disabled
            title="Модель в attention у вахты"
          >
            <code>{shortId(row.model_id)}</code>
          </button>
        ))}
      </div>
      <button
        type="button"
        className="composer-live-refresh"
        disabled={busy}
        onClick={() => void refresh()}
      >
        {busy ? "…" : "пульс"}
      </button>
      {error ? (
        <span className="composer-live-empty" role="status">
          {error}
        </span>
      ) : null}
    </section>
  );
}

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
  return tail.length > 32 ? `${tail.slice(0, 30)}…` : tail;
}

export function LiveWhoToAsk({ selectedId, catalogIds, onPick }: Props) {
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

  const live = (pulse?.ranking ?? []).filter((row) => !row.avoid).slice(0, 4);
  const avoid = pulse?.attention.slice(0, 2) ?? [];
  const extras: LiveModelRow[] =
    live.length === 0
      ? catalogIds.filter((id) => id && id !== "auto").slice(0, 3).map((model_id) => ({ model_id, avoid: false }))
      : [];
  const takeRows = live.length ? live : extras;
  const fromCatalog = live.length === 0 && extras.length > 0;
  const leader = takeRows[0];
  const alts = takeRows.slice(1);
  const pinned = Boolean(selectedId && takeRows.some((row) => row.model_id === selectedId));
  const phase = busy ? "busy" : error ? "error" : pulse ? "ready" : "idle";

  return (
    <section className="live-who" aria-label="Кому писать сейчас" data-phase={phase} data-picked={pinned ? "1" : "0"}>
      <p className="live-who-kicker">Кому писать сейчас</p>
      <p className="live-who-source">
        Стенд смотрит, кто живой. Источник: пульс моделей · MCP <code>models</code>
      </p>

      {leader ? (
        <>
          <p className="live-who-lead">
            <code>{shortId(leader.model_id)}</code>
          </p>
          <p className="live-who-why">
            {fromCatalog
              ? "Рейтинг пуст — берём из каталога, пока пульс молчит."
              : leader.score != null
                ? `Лидер за сутки · score ${leader.score}`
                : "Лидер по пульсу стенда."}
            {pinned ? " · выбрана для этого чата" : ""}
          </p>
          <div className="live-who-actions">
            <button type="button" className="live-who-cta" onClick={() => onPick(leader.model_id)}>
              Писать {shortId(leader.model_id)}
            </button>
            <button type="button" className="live-who-quiet" onClick={() => onPick("")}>
              Авто
            </button>
            <button type="button" className="live-who-refresh" disabled={busy} onClick={() => void refresh()}>
              {busy ? "обновляем…" : "Обновить пульс"}
            </button>
          </div>
        </>
      ) : (
        <p className="live-who-why" role="status">
          {busy ? "Спрашиваем стенд, кто живой…" : error ?? "Пульс ещё не пришёл. Селект моделей внизу на месте."}
        </p>
      )}

      {alts.length > 0 ? (
        <div className="live-who-alts" data-lane="live">
          <p>Ещё живые</p>
          <div className="live-who-chips">
            {alts.map((row) => (
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
          </div>
        </div>
      ) : null}

      <div className="live-who-alts" data-lane="avoid">
        <p>Не брать</p>
        {avoid.length === 0 ? (
          <span className="composer-live-empty">Сейчас никто не сыпется</span>
        ) : (
          <div className="live-who-chips">
            {avoid.map((row) => (
              <button
                key={row.model_id}
                type="button"
                className="composer-live-chip"
                data-state="avoid"
                disabled
              >
                <code>{shortId(row.model_id)}</code>
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

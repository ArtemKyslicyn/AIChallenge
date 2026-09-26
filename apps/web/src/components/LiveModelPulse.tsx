import { useCallback, useMemo, useState } from "react";

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
  return tail.length > 36 ? `${tail.slice(0, 34)}…` : tail;
}

function clockNow(): string {
  return new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function LiveModelPulse({ selectedId, catalogIds, onPick }: Props) {
  const [pulse, setPulse] = useState<LiveModelPulseDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [takenAt, setTakenAt] = useState<string | null>(null);
  const [pulseCount, setPulseCount] = useState(0);

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setPulse(await fetchLiveModelPulse());
      setTakenAt(clockNow());
      setPulseCount((n) => n + 1);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "пульс недоступен");
    } finally {
      setBusy(false);
    }
  }, []);

  const avoidIds = new Set(pulse?.attention.map((row) => row.model_id) ?? []);
  const live = (pulse?.ranking ?? []).filter((row) => !row.avoid).slice(0, 4);
  const avoid = pulse?.attention.slice(0, 3) ?? [];
  const selectedAvoid = Boolean(selectedId && avoidIds.has(selectedId));
  const leader = live[0];
  const catalogFallback: LiveModelRow[] =
    live.length === 0 && avoid.length === 0 && pulse
      ? catalogIds.filter((id) => id && id !== "auto").slice(0, 4).map((model_id) => ({ model_id, avoid: false }))
      : [];
  const takeRows = live.length ? live : catalogFallback;
  const fromCatalog = live.length === 0 && catalogFallback.length > 0;
  const pinnedFromPulse = Boolean(selectedId && takeRows.some((row) => row.model_id === selectedId));

  const phase = busy ? "busy" : error ? "error" : !pulse ? "idle" : pinnedFromPulse ? "pinned" : "ready";

  const nowLabel = selectedId ? shortId(selectedId) : "Авто — модель ещё не выбрана";
  const status = useMemo(() => {
    if (busy) return "Снимаем пульс MCP… ждём model_pulse";
    if (error) return `Пульс не пришёл. Старый список моделей на месте. ${error}`;
    if (!pulse) return "Стенд на связи. Нажмите «Снять пульс» — чат спросит MCP.";
    if (pinnedFromPulse) return `Пин стоит. Ответ в чат пойдёт от ${shortId(selectedId)}.`;
    return "Пульс снят. Нажмите зелёную модель — она станет пином чата.";
  }, [busy, error, pulse, pinnedFromPulse, selectedId]);

  return (
    <section
      className="composer-live-pulse"
      aria-label="Живой выбор модели"
      data-phase={phase}
      data-pulse-count={String(pulseCount)}
    >
      <header className="composer-live-head">
        <p className="composer-live-stamp">Чат · живой выбор</p>
        <h2 className="composer-live-title">Стенд сам говорит, какую модель брать</h2>
        <p className="composer-live-source">
          Источник: MCP · сервер <code>models</code> · инструмент <code>model_pulse</code>
        </p>
      </header>

      <ol className="composer-live-steps">
        <li data-done={pulse || busy ? "1" : "0"}>1. Стенд на связи</li>
        <li data-done={pulse ? "1" : "0"}>2. Снять пульс</li>
        <li data-done={pinnedFromPulse ? "1" : "0"}>3. Выбрать живую</li>
      </ol>

      <div className="composer-live-now" data-picked={pinnedFromPulse ? "1" : "0"}>
        <p className="composer-live-now-kicker">Сейчас в чат пойдёт</p>
        <p className="composer-live-now-id">
          <code>{nowLabel}</code>
        </p>
        <p className="composer-live-status" role="status">
          {status}
        </p>
      </div>

      <div className="composer-live-toolbar">
        <button
          type="button"
          className="composer-live-refresh"
          disabled={busy}
          onClick={() => void refresh()}
        >
          {busy ? "Снимаем пульс…" : pulseCount > 0 ? "Снять пульс ещё раз" : "Снять пульс"}
        </button>
        {takenAt ? (
          <p className="composer-live-taken">
            Снимок №{pulseCount} в {takenAt}
          </p>
        ) : (
          <p className="composer-live-taken">Снимка ещё не было</p>
        )}
      </div>

      {error ? (
        <p className="composer-live-empty" role="status">
          Пульс не пришёл — селект моделей ниже как был. {error}
        </p>
      ) : pulse ? (
        <div className="composer-live-lanes">
          <div className="composer-live-lane" data-lane="live">
            <p className="composer-live-lane-title">Брать — живые</p>
            <p className="composer-live-lane-sub">
              {fromCatalog ? "Рейтинг пуст, показываем каталог" : "Клик ставит пин в селект «Модель»"}
            </p>
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
                  {row.score != null ? <span>score {row.score}</span> : null}
                </button>
              ))}
            </div>
          </div>
          <div className="composer-live-lane" data-lane="avoid">
            <p className="composer-live-lane-title">Не брать — сыплются</p>
            <p className="composer-live-lane-sub">Вахта models · кликнуть нельзя</p>
            <div className="composer-live-chips">
              {avoid.length === 0 ? (
                <span className="composer-live-empty">Сейчас никто в attention</span>
              ) : (
                avoid.map((row) => (
                  <button
                    key={row.model_id}
                    type="button"
                    className="composer-live-chip"
                    data-state="avoid"
                    disabled
                    title="Модель в attention у вахты"
                  >
                    <code>{shortId(row.model_id)}</code>
                    {row.down_rate != null ? <span>down {row.down_rate}</span> : null}
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      ) : (
        <p className="composer-live-empty" data-wait="pulse">
          Список появится после пульса. Вкладка MCP со старыми днями на месте.
        </p>
      )}

      {selectedAvoid && leader ? (
        <p className="composer-live-warn">
          Выбранная модель сыпется.{" "}
          <button type="button" onClick={() => onPick(leader.model_id)}>
            Взять лидера {shortId(leader.model_id)}
          </button>
        </p>
      ) : null}
    </section>
  );
}

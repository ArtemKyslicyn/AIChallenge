import { useCallback, useMemo } from "react";

import { countWords } from "../generationPrefs";
import type { TempJudgeScorecard } from "../strategies/tempJudge";
import {
  TEMP_SLOT_IDS,
  formatTemp,
  slotDefsFromTemps,
  type TempSlotId,
} from "../strategies/tempStudio";
import type { TempStudioTurn } from "../types";
import { EMPTY_PROBE_SLOT } from "../types";
import { ProbePane } from "./ProbePane";

interface Props {
  turn: TempStudioTurn;
}

function axisCell(
  scores: TempJudgeScorecard["scores"],
  id: TempSlotId,
  axis: "accuracy" | "creativity" | "diversity",
): string {
  const v = scores[id]?.[axis];
  return typeof v === "number" ? String(v) : "—";
}

function accentToPane(
  accent: "cold" | "warm" | "hot",
): "neutral" | "steps" | "experts" {
  if (accent === "cold") return "neutral";
  if (accent === "warm") return "steps";
  return "experts";
}

const AXIS_LABELS = {
  accuracy: "Точность",
  creativity: "Креатив",
  diversity: "Разнообразие",
} as const;

type AxisKey = keyof typeof AXIS_LABELS;

function winnerForAxis(
  scores: TempJudgeScorecard["scores"],
  axis: AxisKey,
): TempSlotId | null {
  let bestId: TempSlotId | null = null;
  let best = -1;
  for (const id of TEMP_SLOT_IDS) {
    const v = scores[id]?.[axis];
    if (typeof v === "number" && v > best) {
      best = v;
      bestId = id;
    }
  }
  return bestId;
}

function axisWinsForSlot(
  scores: TempJudgeScorecard["scores"],
  id: TempSlotId,
): string[] {
  return (Object.keys(AXIS_LABELS) as AxisKey[])
    .filter((axis) => winnerForAxis(scores, axis) === id)
    .map((axis) => AXIS_LABELS[axis]);
}

export function TempStudioTurnView({ turn }: Props) {
  const temps = turn.temps ?? { t0: 0, t07: 0.7, t12: 1.2 };
  const defs = useMemo(
    () => slotDefsFromTemps([temps.t0, temps.t07, temps.t12]),
    [temps.t0, temps.t07, temps.t12],
  );
  const done = TEMP_SLOT_IDS.every((id) => !turn.slots[id].loading);
  const judging = Boolean(turn.judgeLoading);
  const judge = turn.judge;
  const frameAnchor = (id: TempSlotId) => `temp-${turn.id}-${id}`;
  const verdictAnchor = `temp-${turn.id}-verdict`;

  const winnerStrip = useMemo(() => {
    if (!judge?.scores) return [];
    return (Object.keys(AXIS_LABELS) as AxisKey[]).flatMap((axis) => {
      const id = winnerForAxis(judge.scores, axis);
      if (!id) return [];
      const def = defs.find((d) => d.id === id);
      return [{ axis, label: AXIS_LABELS[axis], tempLabel: def?.label ?? id }];
    });
  }, [defs, judge]);

  const exportJson = useCallback(() => {
    const payload = {
      kind: "temp_studio",
      task: turn.taskDisplay,
      exportedAt: new Date().toISOString(),
      temperatures: defs.map((def) => {
        const slot = turn.slots[def.id];
        return {
          id: def.id,
          temperature: def.temperature,
          model_id: slot.modelId,
          words: countWords(slot.content),
          latency_ms: slot.latencyMs ?? null,
          content: slot.content,
          error: slot.error,
          scores: turn.judge?.scores?.[def.id] ?? null,
          best_for: turn.judge?.bestFor?.[def.id] ?? null,
        };
      }),
      judge: turn.judge ?? null,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `temp-studio-${turn.id.slice(-8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [defs, turn]);

  const readyCount = TEMP_SLOT_IDS.filter((id) => !turn.slots[id].loading).length;
  const tempLabels = defs.map((d) => formatTemp(d.temperature)).join(" · ");

  return (
    <article
      className="turn temp-studio-turn"
      id={`temp-${turn.id}`}
      aria-label={`Студия температуры: ${tempLabels}`}
    >
      <header className="lab-turn-head">
        <div>
          <p className="temp-studio-kicker">Режим ×T · temperature</p>
          <h2 className="lab-turn-title">Студия температуры</h2>
          <p className="lab-turn-task">{turn.taskDisplay}</p>
          <p className="temp-studio-note">
            Размышление (thinking) принудительно выключено — иначе DeepSeek игнорирует
            temperature.
          </p>
          <nav className="temp-studio-run-temps" aria-label="Перейти к температуре">
            {defs.map((def) => (
              <a
                key={def.id}
                href={`#${frameAnchor(def.id)}`}
                className={`temp-studio-pill temp-studio-pill--${def.accent}`}
              >
                {def.label}
              </a>
            ))}
            {done && judge && !judging && (
              <a href={`#${verdictAnchor}`} className="temp-studio-jump-verdict">
                ↓ Выводы
              </a>
            )}
          </nav>
          {done && judge && !judging && winnerStrip.length > 0 && (
            <p className="temp-studio-winner-strip" aria-label="Лучшие по осям">
              {winnerStrip.map((w) => (
                <span key={w.axis}>
                  {w.label} → {w.tempLabel}
                </span>
              ))}
            </p>
          )}
          {!done && (
            <p className="lab-turn-progress">
              {readyCount}/3 ответа… Один запрос, три значения temperature.
            </p>
          )}
          {done && judging && (
            <p className="lab-turn-progress">
              <span className="spinner" aria-hidden="true" /> Сравниваем точность, креатив и
              разнообразие…
            </p>
          )}
        </div>
        <div className="lab-turn-actions">
          <button type="button" className="ghost-button" onClick={exportJson} disabled={!done}>
            Экспорт JSON
          </button>
        </div>
      </header>

      <div className="temp-studio-stack">
        {defs.map((def) => {
          const wins =
            judge && !judging ? axisWinsForSlot(judge.scores, def.id) : [];
          return (
            <section
              key={def.id}
              id={frameAnchor(def.id)}
              className={`temp-studio-frame temp-studio-frame--${def.accent}`}
              aria-label={`${def.label}: ${def.hint}`}
            >
              <div className="temp-studio-frame-badge">
                <div className="temp-studio-frame-badge-main">
                  <span className="temp-studio-frame-t">{def.label}</span>
                  <span className="temp-studio-frame-hint">{def.hint}</span>
                </div>
                {wins.length > 0 && (
                  <span className="temp-studio-frame-wins">
                    лучше: {wins.join(" · ")}
                  </span>
                )}
              </div>
              <div className="temp-studio-frame-body">
                <ProbePane
                  title="Ответ модели"
                  subtitle={undefined}
                  slot={turn.slots[def.id]}
                  accent={accentToPane(def.accent)}
                />
              </div>
            </section>
          );
        })}
      </div>

      {done && judge && !judging && (
        <section
          id={verdictAnchor}
          className="temp-studio-verdict"
          aria-label="Автооценка температур"
        >
          <header className="temp-studio-verdict-head">
            <h3>Выводы</h3>
            {judge.modelId && <span className="badge">{judge.modelId}</span>}
            {judge.heuristic && (
              <span className="temp-studio-heuristic" title={judge.error ?? undefined}>
                эвристика
              </span>
            )}
          </header>

          {judge.error && !judge.heuristic && (
            <p className="compare-error">{judge.error}</p>
          )}
          {judge.error && judge.heuristic && (
            <p className="compare-pane-muted">{judge.error}</p>
          )}

          <div className="temp-studio-table-wrap">
            <table className="lab-results-table temp-studio-table">
              <caption className="sr-only">
                Оценки точности, креативности и разнообразия по температурам
              </caption>
              <thead>
                <tr>
                  <th scope="col">Ось</th>
                  {defs.map((def) => (
                    <th key={def.id} scope="col">
                      {def.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Точность</th>
                  {TEMP_SLOT_IDS.map((id) => (
                    <td key={id} className="lab-results-score">
                      {axisCell(judge.scores, id, "accuracy")}
                    </td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">Креатив</th>
                  {TEMP_SLOT_IDS.map((id) => (
                    <td key={id} className="lab-results-score">
                      {axisCell(judge.scores, id, "creativity")}
                    </td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">Разнообразие</th>
                  {TEMP_SLOT_IDS.map((id) => (
                    <td key={id} className="lab-results-score">
                      {axisCell(judge.scores, id, "diversity")}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>

          <ul className="temp-studio-tips">
            {defs.map((def) => (
              <li key={def.id}>
                <strong>{def.label}</strong>
                {" — "}
                {judge.bestFor[def.id] ?? "нет рекомендации"}
              </li>
            ))}
          </ul>

          {judge.summary && <p className="temp-studio-summary">{judge.summary}</p>}
        </section>
      )}
    </article>
  );
}

export function emptyTempStudioSlots(
  temps: [number, number, number] = [0, 0.7, 1.2],
): TempStudioTurn["slots"] {
  const defs = slotDefsFromTemps(temps);
  const slots = {} as TempStudioTurn["slots"];
  for (const def of defs) {
    slots[def.id] = {
      ...EMPTY_PROBE_SLOT,
      statusHint: `temperature ${formatTemp(def.temperature)}…`,
    };
  }
  return slots;
}

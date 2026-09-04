import { useCallback } from "react";

import { countWords, hasExpertSections, hasNumberedSteps } from "../generationPrefs";
import { PROMPT_STRATEGIES, strategyById } from "../strategies/definitions";
import type { PromptStrategyId } from "../strategies/types";
import type { LabTurn } from "../types";
import { ProbePane } from "./ProbePane";

interface Props {
  turn: LabTurn;
  onOpenResults?: () => void;
  expanded?: boolean;
  onToggleExpand?: () => void;
}

export function LabTurnView({ turn, onOpenResults, expanded = true, onToggleExpand }: Props) {
  const done = Object.values(turn.slots).every((s) => !s.loading);
  const frameAnchor = (id: PromptStrategyId) => `lab-${turn.id}-${id}`;

  const exportJson = useCallback(() => {
    const payload = {
      task: turn.taskDisplay,
      exportedAt: new Date().toISOString(),
      judge: turn.judge ?? null,
      strategies: PROMPT_STRATEGIES.map((def) => {
        const slot = turn.slots[def.id];
        return {
          id: def.id,
          label: def.label,
          model_id: slot.modelId,
          words: countWords(slot.content),
          latency_ms: slot.latencyMs ?? null,
          hasSteps: hasNumberedSteps(slot.content),
          hasExperts: hasExpertSections(slot.content),
          metaPrompt: slot.metaPrompt ?? null,
          expertSlots: slot.expertSlots ?? null,
          content: slot.content,
          error: slot.error,
          score: turn.judge?.scores?.[def.id] ?? null,
        };
      }),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `prompt-lab-${turn.id.slice(-8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [turn]);

  const winnerId = turn.judge?.winnerId;
  const winner =
    winnerId && PROMPT_STRATEGIES.find((s) => s.id === winnerId)?.label;

  return (
    <article
      className="turn lab-turn"
      id={`lab-${turn.id}`}
      aria-label="Лаборатория: четыре стратегии промпта"
    >
      <header className="lab-turn-head">
        <div>
          <h2 className="lab-turn-title">Лаборатория промптов</h2>
          <p className="lab-turn-task">{turn.taskDisplay}</p>
          <nav className="lab-run-strategies" aria-label="Перейти к стратегии">
            {PROMPT_STRATEGIES.map((def) => (
              <a
                key={def.id}
                href={`#${frameAnchor(def.id)}`}
                className={`lab-strategy-pill lab-strategy-pill--${def.accent}${
                  winnerId === def.id ? " lab-strategy-pill--winner" : ""
                }`}
              >
                {def.shortLabel}
              </a>
            ))}
          </nav>
          {done && winner && (
            <p className="lab-turn-winner">
              Вердикт судьи: <strong>{winner}</strong>
              {turn.judge?.rationale ? ` — ${turn.judge.rationale}` : ""}
            </p>
          )}
          {!done && (
            <p className="lab-turn-progress">
              {Object.values(turn.slots).filter((s) => !s.loading).length}/4 готово…
            </p>
          )}
        </div>
        <div className="lab-turn-actions">
          {onToggleExpand && (
            <button type="button" className="ghost-button" onClick={onToggleExpand}>
              {expanded ? "Свернуть ответы" : "Развернуть ответы"}
            </button>
          )}
          {done && onOpenResults && (
            <button type="button" className="ghost-button" onClick={onOpenResults}>
              Результаты
            </button>
          )}
          <button type="button" className="ghost-button" onClick={exportJson}>
            Экспорт JSON
          </button>
        </div>
      </header>

      {expanded && (
        <div className="lab-stack">
          {PROMPT_STRATEGIES.map((def) => {
            const isWinner = winnerId === def.id;
            const score = turn.judge?.scores?.[def.id];
            return (
              <section
                key={def.id}
                id={frameAnchor(def.id)}
                className={`lab-frame lab-frame--${def.accent}${
                  isWinner ? " lab-frame--winner" : ""
                }`}
                aria-label={`${def.label}: ${def.hint}`}
              >
                <div className="lab-frame-badge">
                  <div className="lab-frame-badge-main">
                    <span className="lab-frame-title">{def.label}</span>
                    <span className="lab-frame-hint">{def.hint}</span>
                  </div>
                  <div className="lab-frame-badge-meta">
                    {typeof score === "number" && (
                      <span className="lab-frame-score" title="Оценка судьи">
                        {score}
                      </span>
                    )}
                    {isWinner && <span className="lab-frame-wins">победитель</span>}
                  </div>
                </div>
                <div className="lab-frame-body">
                  <ProbePane
                    title={def.shortLabel}
                    subtitle={undefined}
                    slot={turn.slots[def.id]}
                    accent={def.accent}
                    showChecks={def.id === "step_by_step" || def.id === "expert_panel"}
                    checkKind="strategy"
                    compactBody={Boolean(turn.compact)}
                  />
                </div>
              </section>
            );
          })}
        </div>
      )}
    </article>
  );
}

export function emptyLabSlots(): LabTurn["slots"] {
  const slots = {} as LabTurn["slots"];
  for (const id of ["direct", "step_by_step", "meta_prompt", "expert_panel"] as PromptStrategyId[]) {
    slots[id] = {
      loading: true,
      error: null,
      content: "",
      modelId: null,
      statusHint: strategyById(id).id === "meta_prompt" ? "Фаза 1…" : null,
      expertSlots:
        id === "expert_panel"
          ? [
              { id: "analyst", label: "Аналитик", content: "", model_id: null, error: null, loading: true },
              { id: "engineer", label: "Инженер", content: "", model_id: null, error: null, loading: true },
              { id: "critic", label: "Критик", content: "", model_id: null, error: null, loading: true },
              { id: "synthesis", label: "Итог", content: "", model_id: null, error: null, loading: false },
            ]
          : undefined,
    };
  }
  return slots;
}

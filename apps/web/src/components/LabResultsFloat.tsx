import { useCallback, useEffect, useId, useRef } from "react";

import { PROMPT_STRATEGIES } from "../strategies/definitions";
import type { JudgeScorecard } from "../strategies/judge";
import type { PromptStrategyId } from "../strategies/types";

export interface LabResultsPayload {
  labId: string;
  task: string;
  judge: JudgeScorecard | null;
  rows: {
    id: PromptStrategyId;
    modelId: string | null;
    words: number;
    latencyMs?: number;
    error: string | null;
  }[];
}

interface Props {
  open: boolean;
  payload: LabResultsPayload | null;
  onClose: () => void;
  onExpand: () => void;
  onJumpToLab?: () => void;
}

export function LabResultsFloat({ open, payload, onClose, onExpand, onJumpToLab }: Props) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const fabRef = useRef<HTMLButtonElement>(null);
  // Set only when the user closes the panel from inside it (Escape / «Свернуть»),
  // so a mutex-driven collapse never yanks focus back to this FAB.
  const restoreFocus = useRef(false);

  const collapse = useCallback(() => {
    restoreFocus.current = true;
    onClose();
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") collapse();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, collapse]);

  useEffect(() => {
    if (open || !restoreFocus.current) return;
    restoreFocus.current = false;
    fabRef.current?.focus();
  }, [open]);

  if (!payload) return null;

  if (!open) {
    return (
      <button
        ref={fabRef}
        type="button"
        className="lab-results-fab"
        id="lab-results-fab"
        aria-expanded={false}
        aria-controls="lab-results-float-panel"
        aria-label="Открыть результаты лаборатории"
        onClick={onExpand}
      >
        Результаты
      </button>
    );
  }

  const winnerLabel =
    PROMPT_STRATEGIES.find((s) => s.id === payload.judge?.winnerId)?.label ?? "—";

  return (
    <aside
      id="lab-results-float-panel"
      className="lab-results-float"
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
    >
      <header className="lab-results-float-head">
        <div>
          <h2 id={titleId} className="lab-results-float-title">
            Результаты
          </h2>
          <p className="lab-results-float-task">{payload.task}</p>
        </div>
        <div className="lab-results-float-actions">
          {onJumpToLab && (
            <button type="button" className="ghost-button" onClick={onJumpToLab}>
              К лабораторной
            </button>
          )}
          <button
            ref={closeRef}
            type="button"
            className="ghost-button"
            onClick={collapse}
          >
            Свернуть
          </button>
        </div>
      </header>

      <div className="lab-results-verdict">
        {payload.judge?.error ? (
          <span className="lab-results-verdict-warn">Судья: {payload.judge.error}</span>
        ) : (
          <>
            <span>
              Победитель: <strong>{winnerLabel}</strong>
            </span>
            {payload.judge?.modelId && (
              <span className="badge">{payload.judge.modelId}</span>
            )}
          </>
        )}
        {payload.judge?.rationale && (
          <p className="lab-results-rationale">{payload.judge.rationale}</p>
        )}
      </div>

      <div className="lab-results-table-wrap">
        <table className="lab-results-table">
          <thead>
            <tr>
              <th>Стратегия</th>
              <th>Балл</th>
              <th>Модель</th>
              <th>Заметки</th>
            </tr>
          </thead>
          <tbody>
            {PROMPT_STRATEGIES.map((def) => {
              const row = payload.rows.find((r) => r.id === def.id);
              const score = payload.judge?.scores?.[def.id];
              const isWinner = payload.judge?.winnerId === def.id;
              return (
                <tr key={def.id} data-winner={isWinner ? "true" : "false"}>
                  <td>{def.shortLabel}</td>
                  <td className="lab-results-score">{score ?? "—"}</td>
                  <td>{row?.modelId ?? "—"}</td>
                      <td>
                    {row?.error
                      ? row.error.length > 48
                        ? `${row.error.slice(0, 48)}…`
                        : row.error
                      : row?.latencyMs
                        ? `${row.words} сл. · ${row.latencyMs} мс`
                        : `${row?.words ?? 0} сл.`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {payload.judge?.accuracyNotes && (
        <details className="lab-results-notes">
          <summary>Почему так</summary>
          <p>{payload.judge.accuracyNotes}</p>
        </details>
      )}
    </aside>
  );
}

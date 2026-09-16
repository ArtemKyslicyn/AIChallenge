import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { ApiError, runAgentBattleSSE, type AgentBattleEvent } from "../api/client";
import { clearMapPositions } from "../battle/mapPersist";
import { loadArena, resetDefaultArena, saveArena } from "../battle/persist";
import type {
  AgentPersona,
  ArenaDoc,
  EditorTab,
  LogEntry,
  NuclearPosture,
} from "../battle/types";
import { BattleWorldMap, type MapAgentCaption } from "./BattleWorldMap";

function meter(value: number): string {
  return `${Math.round(Math.max(0, Math.min(100, value)))}%`;
}

function applyBattleEvent(
  event: AgentBattleEvent,
  setLog: Dispatch<SetStateAction<LogEntry[]>>,
  setWorld: Dispatch<SetStateAction<Record<string, unknown>>>,
  setScores: Dispatch<SetStateAction<Record<string, number>>>,
  setRunning: Dispatch<SetStateAction<boolean>>,
): void {
  switch (event.type) {
    case "battle_start":
      setWorld(event.world);
      setLog((prev) => [
        ...prev,
        { kind: "system", text: `Старт: ${event.name} · раундов ≤ ${event.max_rounds}` },
      ]);
      break;
    case "round_start":
      setWorld(event.world);
      setLog((prev) => [...prev, { kind: "system", text: `Раунд ${event.round}` }]);
      break;
    case "phase":
      setLog((prev) => [
        ...prev,
        { kind: "phase", round: event.round, phase: event.phase },
      ]);
      break;
    case "agent_done":
      setLog((prev) => [
        ...prev,
        {
          kind: "agent",
          round: event.round,
          phase: event.phase,
          agent_id: event.agent_id,
          name: event.name,
          content: event.content,
          model_id: event.model_id,
          skipped: event.skipped,
          skip_reason: event.skip_reason,
        },
      ]);
      break;
    case "verdict": {
      setWorld(event.world);
      setScores((prev) => {
        const merged = { ...prev };
        for (const s of event.scores) {
          merged[s.agent_id] = (merged[s.agent_id] || 0) + s.points;
        }
        return merged;
      });
      setLog((prev) => [
        ...prev,
        {
          kind: "verdict",
          round: event.round,
          red_line: event.red_line,
          rationale: event.rationale,
          model_id: event.model_id,
          scores: event.scores,
          world: event.world,
        },
      ]);
      break;
    }
    case "world_update":
      setWorld(event.world);
      break;
    case "battle_done":
      setWorld(event.world);
      setRunning(false);
      setLog((prev) => [
        ...prev,
        {
          kind: "done",
          leaderboard: event.leaderboard,
          goals_revealed: event.goals_revealed,
          world: event.world,
        },
      ]);
      break;
    case "error":
      setRunning(false);
      setLog((prev) => [...prev, { kind: "error", message: event.message }]);
      break;
  }
}

export function AgentBattle() {
  const [arena, setArena] = useState<ArenaDoc>(() => loadArena());
  const [tab, setTab] = useState<EditorTab>("world");
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("");
  const [log, setLog] = useState<LogEntry[]>([]);
  const [liveWorld, setLiveWorld] = useState<Record<string, unknown>>({});
  const [scores, setScores] = useState<Record<string, number>>({});
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    saveArena(arena);
  }, [arena]);

  const updatePersona = (id: string, patch: Partial<AgentPersona>) => {
    setArena((prev) => ({
      ...prev,
      cast: prev.cast.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    }));
  };

  const onReset = () => {
    if (running) return;
    const fresh = resetDefaultArena();
    clearMapPositions();
    setArena(fresh);
    setLog([]);
    setScores({});
    setLiveWorld({});
    setSelectedAgentId(null);
    setStatus("Арена сброшена к дефолту");
  };

  const onStop = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setRunning(false);
    setStatus("Остановлено — частичный лог сохранён");
  };

  const onRun = async () => {
    if (running) return;
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setRunning(true);
    setStatus("Идёт прогон…");
    setLog([]);
    setScores({});
    setSelectedAgentId(null);
    setLiveWorld({
      stability: arena.world.stability,
      public_panic: arena.world.public_panic,
      tech_lead: arena.world.tech_lead,
      nuclear_posture: arena.world.nuclear_posture,
    });
    try {
      await runAgentBattleSSE(
        arena,
        (event) => {
          applyBattleEvent(event, setLog, setLiveWorld, setScores, setRunning);
        },
        ctrl.signal,
      );
      if (!ctrl.signal.aborted) setStatus("Готово");
    } catch (err) {
      if (ctrl.signal.aborted) return;
      const msg = err instanceof ApiError ? err.message : "Ошибка запуска битвы";
      setLog((prev) => [...prev, { kind: "error", message: msg }]);
      setStatus(msg);
      setRunning(false);
    } finally {
      abortRef.current = null;
    }
  };

  const stability = Number(liveWorld.stability ?? arena.world.stability);
  const panic = Number(liveWorld.public_panic ?? arena.world.public_panic);
  const techLead =
    (liveWorld.tech_lead as Record<string, number> | undefined) ?? arena.world.tech_lead;

  const focusAgentId = useMemo(() => {
    for (let i = log.length - 1; i >= 0; i -= 1) {
      const entry = log[i];
      if (entry.kind === "agent" && !entry.skipped) return entry.agent_id;
    }
    return null;
  }, [log]);

  const phase = useMemo(() => {
    for (let i = log.length - 1; i >= 0; i -= 1) {
      const entry = log[i];
      if (entry.kind === "phase") return entry.phase;
      if (entry.kind === "agent") return entry.phase;
    }
    return null;
  }, [log]);

  const round = useMemo(() => {
    for (let i = log.length - 1; i >= 0; i -= 1) {
      const entry = log[i];
      if (entry.kind === "phase") return entry.round;
      if (entry.kind === "agent") return entry.round;
      if (entry.kind === "verdict") return entry.round;
    }
    return null;
  }, [log]);

  const skippedIds = useMemo(() => {
    const ids = new Set<string>();
    for (const entry of log) {
      if (entry.kind === "agent" && entry.skipped) ids.add(entry.agent_id);
    }
    return ids;
  }, [log]);

  const captions = useMemo(() => {
    const latest = new Map<string, MapAgentCaption>();
    for (const entry of log) {
      if (entry.kind !== "agent") continue;
      latest.set(entry.agent_id, {
        agentId: entry.agent_id,
        text: entry.content,
        phase: entry.phase,
        skipped: entry.skipped,
      });
    }
    return [...latest.values()];
  }, [log]);

  const redLine = useMemo(() => {
    if (liveWorld.red_line_crossed) return true;
    for (let i = log.length - 1; i >= 0; i -= 1) {
      const entry = log[i];
      if (entry.kind === "verdict" && entry.red_line) return true;
    }
    return false;
  }, [log, liveWorld]);

  useEffect(() => {
    if (!selectedAgentId || !logRef.current) return;
    const node = logRef.current.querySelector(
      `[data-agent-id="${CSS.escape(selectedAgentId)}"]`,
    );
    if (node instanceof HTMLElement) {
      node.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [selectedAgentId, log]);

  return (
    <div className="battle-board">
      <div className="battle-board-top">
        <div>
          <h2>Битва агентов</h2>
          <p className="battle-board-sub">
            Песочница кризиса: tech-race и ядерное сдерживание как сюжет. Меняйте мир и факты —
            затем запустите раунды. У каждого хода виден <code>model_id</code>.
          </p>
        </div>
        <div className="battle-board-actions">
          <button type="button" className="ghost-button" disabled={running} onClick={onReset}>
            Сброс
          </button>
          <button type="button" className="ghost-button" disabled={!running} onClick={onStop}>
            Стоп
          </button>
          <button type="button" className="primary-button" disabled={running} onClick={() => void onRun()}>
            {running ? "Идёт…" : "Запуск"}
          </button>
        </div>
      </div>

      {status ? <p className="battle-status">{status}</p> : null}

      <div className="battle-meters" aria-label="Состояние мира">
        <div>
          <span>Стабильность</span>
          <strong>{meter(stability)}</strong>
          <div className="battle-meter-bar">
            <i style={{ width: meter(stability) }} />
          </div>
        </div>
        <div>
          <span>Паника</span>
          <strong>{meter(panic)}</strong>
          <div className="battle-meter-bar battle-meter-bar--panic">
            <i style={{ width: meter(panic) }} />
          </div>
        </div>
      </div>

      <BattleWorldMap
        cast={arena.cast}
        running={running}
        focusAgentId={focusAgentId}
        selectedAgentId={selectedAgentId}
        phase={phase}
        round={round}
        skippedIds={skippedIds}
        scores={scores}
        captions={captions}
        stability={stability}
        panic={panic}
        techLead={techLead}
        redLine={redLine}
        onSelectAgent={setSelectedAgentId}
      />

      <div className="battle-layout">
        <aside className="battle-editors">
          <nav className="battle-tabs" role="tablist" aria-label="Редакторы арены">
            {(
              [
                ["world", "Мир"],
                ["facts", "Факты"],
                ["cast", "Каст"],
                ["rules", "Правила"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                className="battle-tab"
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>

          {tab === "world" ? (
            <div className="battle-editor-pane">
              <label>
                Название
                <input
                  value={arena.name}
                  disabled={running}
                  onChange={(e) => setArena({ ...arena, name: e.target.value })}
                />
              </label>
              <label>
                Эпоха
                <input
                  value={arena.world.era}
                  disabled={running}
                  onChange={(e) =>
                    setArena({ ...arena, world: { ...arena.world, era: e.target.value } })
                  }
                />
              </label>
              <label>
                Сеттинг
                <textarea
                  rows={6}
                  value={arena.world.setting}
                  disabled={running}
                  onChange={(e) =>
                    setArena({ ...arena, world: { ...arena.world, setting: e.target.value } })
                  }
                />
              </label>
              <label>
                Технологии (сюжет)
                <textarea
                  rows={4}
                  value={arena.world.tech_landscape}
                  disabled={running}
                  onChange={(e) =>
                    setArena({
                      ...arena,
                      world: { ...arena.world, tech_landscape: e.target.value },
                    })
                  }
                />
              </label>
              <label>
                Доктрина сдерживания
                <select
                  value={arena.world.nuclear_posture}
                  disabled={running}
                  onChange={(e) =>
                    setArena({
                      ...arena,
                      world: {
                        ...arena.world,
                        nuclear_posture: e.target.value as NuclearPosture,
                      },
                    })
                  }
                >
                  <option value="opaque">opaque</option>
                  <option value="declared">declared</option>
                  <option value="hair_trigger">hair_trigger</option>
                </select>
              </label>
              <div className="battle-inline-fields">
                <label>
                  Stability
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={arena.world.stability}
                    disabled={running}
                    onChange={(e) =>
                      setArena({
                        ...arena,
                        world: { ...arena.world, stability: Number(e.target.value) },
                      })
                    }
                  />
                </label>
                <label>
                  Panic
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={arena.world.public_panic}
                    disabled={running}
                    onChange={(e) =>
                      setArena({
                        ...arena,
                        world: { ...arena.world, public_panic: Number(e.target.value) },
                      })
                    }
                  />
                </label>
              </div>
            </div>
          ) : null}

          {tab === "facts" ? (
            <div className="battle-editor-pane">
              <label>
                Факты (JSON)
                <textarea
                  rows={16}
                  spellCheck={false}
                  value={JSON.stringify(arena.inputs, null, 2)}
                  disabled={running}
                  onChange={(e) => {
                    try {
                      const parsed = JSON.parse(e.target.value) as ArenaDoc["inputs"];
                      setArena({ ...arena, inputs: parsed });
                    } catch {
                      /* keep typing */
                    }
                  }}
                />
              </label>
            </div>
          ) : null}

          {tab === "cast" ? (
            <div className="battle-editor-pane battle-cast-list">
              {arena.cast.map((p) => (
                <details key={p.id} className="battle-persona">
                  <summary>
                    <label className="battle-persona-enable" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={p.enabled}
                        disabled={running}
                        onChange={(e) => updatePersona(p.id, { enabled: e.target.checked })}
                      />
                      {p.name}
                    </label>
                  </summary>
                  <label>
                    Публичная повестка
                    <input
                      value={p.public_agenda}
                      disabled={running}
                      onChange={(e) => updatePersona(p.id, { public_agenda: e.target.value })}
                    />
                  </label>
                  <label>
                    Скрытая цель
                    <input
                      value={p.hidden_goal}
                      disabled={running}
                      onChange={(e) => updatePersona(p.id, { hidden_goal: e.target.value })}
                    />
                  </label>
                  <label>
                    System prompt
                    <textarea
                      rows={4}
                      value={p.system_prompt}
                      disabled={running}
                      onChange={(e) => updatePersona(p.id, { system_prompt: e.target.value })}
                    />
                  </label>
                  <div className="battle-inline-fields">
                    <label>
                      model
                      <input
                        value={p.preferred_model}
                        disabled={running}
                        onChange={(e) =>
                          updatePersona(p.id, { preferred_model: e.target.value || "auto" })
                        }
                      />
                    </label>
                    <label>
                      temp
                      <input
                        type="number"
                        step={0.1}
                        min={0}
                        max={2}
                        value={p.temperature}
                        disabled={running}
                        onChange={(e) =>
                          updatePersona(p.id, { temperature: Number(e.target.value) })
                        }
                      />
                    </label>
                  </div>
                </details>
              ))}
              <label>
                Арбитр (system)
                <textarea
                  rows={5}
                  value={arena.arbiter.system_prompt}
                  disabled={running}
                  onChange={(e) =>
                    setArena({
                      ...arena,
                      arbiter: { ...arena.arbiter, system_prompt: e.target.value },
                    })
                  }
                />
              </label>
            </div>
          ) : null}

          {tab === "rules" ? (
            <div className="battle-editor-pane">
              <div className="battle-inline-fields">
                <label>
                  max_rounds (≤8)
                  <input
                    type="number"
                    min={1}
                    max={8}
                    value={arena.rules.max_rounds}
                    disabled={running}
                    onChange={(e) =>
                      setArena({
                        ...arena,
                        rules: {
                          ...arena.rules,
                          max_rounds: Math.max(1, Math.min(8, Number(e.target.value) || 1)),
                        },
                      })
                    }
                  />
                </label>
                <label>
                  concurrency
                  <input
                    type="number"
                    min={1}
                    max={5}
                    value={arena.rules.concurrency}
                    disabled={running}
                    onChange={(e) =>
                      setArena({
                        ...arena,
                        rules: {
                          ...arena.rules,
                          concurrency: Math.max(1, Math.min(5, Number(e.target.value) || 1)),
                        },
                      })
                    }
                  />
                </label>
              </div>
              <label className="battle-check">
                <input
                  type="checkbox"
                  checked={arena.rules.skip_rebut}
                  disabled={running}
                  onChange={(e) =>
                    setArena({
                      ...arena,
                      rules: { ...arena.rules, skip_rebut: e.target.checked },
                    })
                  }
                />
                Пропустить rebut
              </label>
              <label className="battle-check">
                <input
                  type="checkbox"
                  checked={arena.rules.stop_on_red_line}
                  disabled={running}
                  onChange={(e) =>
                    setArena({
                      ...arena,
                      rules: { ...arena.rules, stop_on_red_line: e.target.checked },
                    })
                  }
                />
                Стоп на red line
              </label>
              <label className="battle-check">
                <input
                  type="checkbox"
                  checked={arena.rules.reveal_hidden_goals}
                  disabled={running}
                  onChange={(e) =>
                    setArena({
                      ...arena,
                      rules: { ...arena.rules, reveal_hidden_goals: e.target.checked },
                    })
                  }
                />
                Показать скрытые цели в конце
              </label>
            </div>
          ) : null}
        </aside>

        <section className="battle-feed" aria-live="polite">
          <h3 className="battle-section-title">Лента и скорборд</h3>
          {Object.keys(scores).length > 0 ? (
            <ul className="battle-scoreboard">
              {Object.entries(scores)
                .sort((a, b) => b[1] - a[1])
                .map(([id, pts]) => {
                  const name = arena.cast.find((c) => c.id === id)?.name || id;
                  return (
                    <li key={id}>
                      <span>{name}</span>
                      <strong>{pts.toFixed(1)}</strong>
                    </li>
                  );
                })}
            </ul>
          ) : (
            <p className="battle-board-muted">Запустите арену — здесь появятся очки и ходы.</p>
          )}

          <div className="battle-log" ref={logRef}>
            {log.map((entry, idx) => {
              if (entry.kind === "system") {
                return (
                  <div key={idx} className="battle-log-card battle-log-card--sys">
                    {entry.text}
                  </div>
                );
              }
              if (entry.kind === "phase") {
                return (
                  <div key={idx} className="battle-log-card battle-log-card--phase">
                    R{entry.round} · {entry.phase}
                  </div>
                );
              }
              if (entry.kind === "agent") {
                const highlighted = selectedAgentId === entry.agent_id;
                return (
                  <article
                    key={idx}
                    data-agent-id={entry.agent_id}
                    className={[
                      "battle-log-card",
                      entry.skipped ? "battle-log-card--skip" : "",
                      highlighted ? "battle-log-card--focus" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    <header>
                      <strong>
                        {entry.name}
                        {entry.skipped ? " · пропуск" : ""}
                      </strong>
                      <code>
                        {entry.skipped
                          ? entry.skip_reason || "skipped"
                          : entry.model_id || "—"}
                      </code>
                    </header>
                    <p>{entry.content}</p>
                  </article>
                );
              }
              if (entry.kind === "verdict") {
                return (
                  <article key={idx} className="battle-log-card battle-log-card--verdict">
                    <header>
                      <strong>Вердикт R{entry.round}</strong>
                      <code>{entry.model_id || "arbiter"}</code>
                    </header>
                    {entry.red_line ? <p className="battle-red">Red line</p> : null}
                    <p>{entry.rationale}</p>
                  </article>
                );
              }
              if (entry.kind === "done") {
                return (
                  <article key={idx} className="battle-log-card battle-log-card--done">
                    <header>
                      <strong>Финиш</strong>
                    </header>
                    <ol>
                      {entry.leaderboard.map((row) => (
                        <li key={row.agent_id}>
                          {row.name}: {row.points.toFixed(1)}
                        </li>
                      ))}
                    </ol>
                    {entry.goals_revealed?.length ? (
                      <ul className="battle-goals">
                        {entry.goals_revealed.map((g) => (
                          <li key={g.agent_id}>
                            <code>{g.agent_id}</code>: {g.hidden_goal}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </article>
                );
              }
              return (
                <div key={idx} className="battle-log-card battle-log-card--err" role="alert">
                  {entry.message}
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}

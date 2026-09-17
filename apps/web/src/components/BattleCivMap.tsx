import { useMemo } from "react";
import { Orientation, defineHex, Grid, hexToPoint, rectangle } from "honeycomb-grid";

import { MEANS_META, type BattleMeans } from "../battle/means";
import type { CabinetVoice } from "../battle/cabinet";
import type { AgentPersona } from "../battle/types";

type Props = {
  cast: AgentPersona[];
  running: boolean;
  focusAgentId: string | null;
  selectedAgentId: string | null;
  phase: string | null;
  round: number | null;
  maxRounds: number;
  lastDelta: string;
  lastMeans: BattleMeans | null;
  lastMeansActor: string | null;
  lastCabinet?: CabinetVoice[];
  cabinetNationId?: string | null;
  scores: Record<string, number>;
  stability: number;
  panic: number;
  techLead: Record<string, number>;
  escalation: number;
  redLine?: boolean;
  winnerLabel?: string | null;
  onSelectAgent?: (agentId: string) => void;
};

const FACTION_COLOR: Record<string, string> = {
  atlantic: "#3d7ea6",
  pacific: "#2f8f6b",
  neutral: "#c4a35a",
};

const CAPITALS: Record<string, { q: number; r: number }> = {
  atlantic: { q: 2, r: 3 },
  pacific: { q: 8, r: 2 },
  neutral: { q: 5, r: 6 },
};

const Tile = defineHex({ dimensions: 22, orientation: Orientation.FLAT });

function axialDist(a: { q: number; r: number }, b: { q: number; r: number }): number {
  return (
    (Math.abs(a.q - b.q) +
      Math.abs(a.q + a.r - b.q - b.r) +
      Math.abs(a.r - b.r)) /
    2
  );
}

function ownerOf(q: number, r: number): string {
  let best = "neutral";
  let bestD = Infinity;
  for (const [id, cap] of Object.entries(CAPITALS)) {
    const d = axialDist({ q, r }, cap);
    if (d < bestD) {
      bestD = d;
      best = id;
    }
  }
  return best;
}

function phaseLabel(phase: string | null): string {
  if (!phase) return "";
  const map: Record<string, string> = {
    brief: "бриф",
    propose: "ходы",
    rebut: "ответ",
    verdict: "вердикт",
    recover: "сбой",
  };
  return map[phase] || phase;
}

export function BattleCivMap({
  cast,
  running,
  focusAgentId,
  selectedAgentId,
  phase,
  round,
  maxRounds,
  lastDelta,
  lastMeans,
  lastMeansActor,
  lastCabinet = [],
  cabinetNationId = null,
  scores,
  stability,
  panic,
  techLead,
  escalation,
  redLine = false,
  winnerLabel,
  onSelectAgent,
}: Props) {
  const fxKey = `${lastMeans ?? "none"}:${lastMeansActor ?? "-"}:${round ?? 0}`;

  const enabled = useMemo(() => cast.filter((c) => c.enabled), [cast]);
  const selected = useMemo(
    () => enabled.find((a) => a.id === (selectedAgentId || cabinetNationId || focusAgentId)),
    [enabled, selectedAgentId, cabinetNationId, focusAgentId],
  );
  const cabinetSeats = selected?.cabinet || [];
  const liveVoices = useMemo(() => {
    if (!lastCabinet.length) return [];
    if (cabinetNationId && selected && cabinetNationId !== selected.id) return [];
    return lastCabinet;
  }, [lastCabinet, cabinetNationId, selected]);

  const { hexes, points, width, height } = useMemo(() => {
    const grid = new Grid(Tile, rectangle({ width: 11, height: 8 }));
    const list: { q: number; r: number; owner: string; corners: string; cx: number; cy: number }[] =
      [];
    let maxX = 0;
    let maxY = 0;
    grid.forEach((hex) => {
      const q = hex.q;
      const r = hex.r;
      const owner = ownerOf(q, r);
      const pt = hexToPoint(hex);
      const corners = hex.corners
        .map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`)
        .join(" ");
      list.push({
        q,
        r,
        owner,
        corners,
        cx: pt.x,
        cy: pt.y,
      });
      maxX = Math.max(maxX, pt.x + 24);
      maxY = Math.max(maxY, pt.y + 24);
    });
    return { hexes: list, points: list, width: maxX + 20, height: maxY + 20 };
  }, []);

  const capitals = useMemo(() => {
    return enabled.map((agent) => {
      const cap = CAPITALS[agent.id] || CAPITALS.neutral;
      const cell = points.find((h) => h.q === cap.q && h.r === cap.r) || points[0];
      return { agent, x: cell?.cx ?? 0, y: cell?.cy ?? 0 };
    });
  }, [enabled, points]);

  const focusCap = capitals.find((c) => c.agent.id === focusAgentId);
  const actorCap = capitals.find((c) => c.agent.id === lastMeansActor);
  const targetId =
    lastMeans === "strike" || lastMeans === "sanctions" || lastMeans === "cyber"
      ? enabled.find((a) => a.id !== lastMeansActor)?.id
      : lastMeans === "diplomacy"
        ? null
        : lastMeansActor;
  const targetCap =
    lastMeans === "diplomacy"
      ? { x: width * 0.48, y: height * 0.42 }
      : capitals.find((c) => c.agent.id === targetId);

  const meansMeta = lastMeans ? MEANS_META[lastMeans] : null;
  const boardClass = [
    "civ-map",
    running ? "civ-map--live" : "",
    redLine ? "civ-map--red" : "",
    lastMeans ? `civ-map--${lastMeans}` : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section className="civ-wrap" aria-label="Карта войны блоков">
      <div className="civ-head">
        <div>
          <h3 className="battle-section-title">Карта войны</h3>
          <p className="battle-world-hint">
            Три страны · кабинет (президент / парламент / оборона / экономика) · гексы · средство хода.
            Практики: Wazir, Qurultai, Pentarchy, Deliberation-in-Silico.
          </p>
        </div>
        <div className="battle-world-meta" aria-live="polite">
          {running ? (
            <span className="battle-world-live">
              LIVE · {round ?? "—"}/{maxRounds}
              {phase ? ` · ${phaseLabel(phase)}` : ""}
            </span>
          ) : (
            <span className="battle-board-muted">ожидание · {maxRounds} шагов</span>
          )}
        </div>
      </div>

      <div className="civ-ticker" aria-live="polite">
        <div>
          <strong>Ход:</strong>{" "}
          {focusCap
            ? `${focusCap.agent.name}${focusCap.agent.preferred_model !== "auto" ? ` · ${focusCap.agent.preferred_model}` : ""}`
            : running
              ? "ждём…"
              : "—"}
          {meansMeta ? (
            <span className="civ-means-chip" style={{ borderColor: meansMeta.hue }}>
              {meansMeta.icon} {meansMeta.label}
            </span>
          ) : null}
        </div>
        <div>
          <strong>Мир Δ:</strong> {lastDelta || "—"}
          {" · "}
          <strong>Эскалация:</strong> {escalation}/5
        </div>
        {winnerLabel ? (
          <div className="civ-winner">
            Победитель войны: <strong>{winnerLabel}</strong>
          </div>
        ) : null}
      </div>

      <div className="civ-factions">
        {enabled.map((agent) => {
          const score = Math.round(Number(techLead[agent.id] ?? 50));
          const pts = scores[agent.id];
          return (
            <button
              key={agent.id}
              type="button"
              className={[
                "civ-faction",
                focusAgentId === agent.id ? "civ-faction--active" : "",
                selectedAgentId === agent.id ? "civ-faction--selected" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              style={{ ["--fac" as string]: FACTION_COLOR[agent.id] || "#888" }}
              onClick={() => onSelectAgent?.(agent.id)}
            >
              <span className="civ-faction-name">{agent.name}</span>
              <strong>{score}</strong>
              <i style={{ width: `${Math.max(8, Math.min(100, score))}%` }} />
              <em>
                {agent.preferred_model === "auto" ? "auto" : agent.preferred_model}
                {pts != null ? ` · ${pts.toFixed(0)} pts` : ""}
              </em>
            </button>
          );
        })}
        <div className="civ-faction civ-faction--meters">
          <span>Стаб. {Math.round(stability)}</span>
          <span>Паника {Math.round(panic)}</span>
        </div>
      </div>

      <div className={boardClass}>
        <svg
          className="civ-svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label="Гексагональная карта блоков"
        >
          <defs>
            <linearGradient id="civ-sea" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#143a48" />
              <stop offset="100%" stopColor="#1a4f4a" />
            </linearGradient>
            <filter id="civ-glow">
              <feGaussianBlur stdDeviation="2.2" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <rect width={width} height={height} fill="url(#civ-sea)" />

          {hexes.map((h) => {
            const power = Number(techLead[h.owner] ?? 50) / 100;
            const base = FACTION_COLOR[h.owner] || "#557";
            const isCap = Object.values(CAPITALS).some((c) => c.q === h.q && c.r === h.r);
            return (
              <polygon
                key={`${h.q},${h.r}`}
                points={h.corners}
                fill={base}
                fillOpacity={0.35 + power * 0.45}
                stroke="rgba(255,245,220,0.22)"
                strokeWidth={isCap ? 2.2 : 0.8}
              />
            );
          })}

          {/* Summit island marker */}
          <circle
            cx={width * 0.48}
            cy={height * 0.42}
            r={10}
            fill="#e8d5a3"
            stroke="#b89a58"
            strokeWidth={1.5}
          />
          <text
            x={width * 0.48}
            y={height * 0.42 + 3}
            textAnchor="middle"
            fontSize={7}
            fill="#2a2418"
          >
            Аэрис
          </text>

          {capitals.map(({ agent, x, y }) => {
            const active = focusAgentId === agent.id;
            const selected = selectedAgentId === agent.id;
            return (
              <g
                key={agent.id}
                transform={`translate(${x}, ${y})`}
                className="civ-capital"
                onClick={() => onSelectAgent?.(agent.id)}
                style={{ cursor: "pointer" }}
              >
                {active ? (
                  <circle r={18} fill="none" stroke="#ffe3a0" strokeWidth={2} className="civ-pulse" />
                ) : null}
                <circle
                  r={11}
                  fill={FACTION_COLOR[agent.id] || "#888"}
                  stroke={selected ? "#fff8e0" : "rgba(255,255,255,0.7)"}
                  strokeWidth={selected ? 2.5 : 1.4}
                  filter={active ? "url(#civ-glow)" : undefined}
                />
                <text y={3} textAnchor="middle" fontSize={8} fill="#fff" fontWeight={700}>
                  {agent.name.slice(0, 1)}
                </text>
              </g>
            );
          })}

          {meansMeta && actorCap && targetCap && lastMeans ? (
            <g key={fxKey} className={`civ-fx civ-fx--${lastMeans}`}>
              {lastMeans === "strike" || lastMeans === "deterrence" ? (
                <path
                  d={`M ${actorCap.x} ${actorCap.y} Q ${(actorCap.x + targetCap.x) / 2} ${Math.min(actorCap.y, targetCap.y) - 40} ${targetCap.x} ${targetCap.y}`}
                  fill="none"
                  stroke={meansMeta.hue}
                  strokeWidth={2.4}
                  strokeDasharray="6 4"
                  className="civ-missile"
                />
              ) : (
                <line
                  x1={actorCap.x}
                  y1={actorCap.y}
                  x2={targetCap.x}
                  y2={targetCap.y}
                  stroke={meansMeta.hue}
                  strokeWidth={2}
                  strokeDasharray={lastMeans === "diplomacy" ? "4 3" : "2 2"}
                  className="civ-link"
                />
              )}
              {(lastMeans === "strike" || lastMeans === "cyber") && (
                <circle
                  cx={targetCap.x}
                  cy={targetCap.y}
                  r={16}
                  fill="none"
                  stroke={meansMeta.hue}
                  strokeWidth={2}
                  className="civ-blast"
                />
              )}
            </g>
          ) : null}
        </svg>
        {escalation >= 3 ? <div className="civ-escalation-fog" aria-hidden /> : null}
      </div>

      {selected ? (
        <div className="civ-cabinet" aria-label={`Кабинет ${selected.name}`}>
          <div className="civ-cabinet-head">
            <strong>Кабинет · {selected.name}</strong>
            <span>
              {selected.preferred_model === "auto" ? "auto" : selected.preferred_model}
            </span>
          </div>
          <div className="civ-cabinet-grid">
            {cabinetSeats.map((seat) => {
              const voice = liveVoices.find((v) => v.role === seat.role);
              return (
                <article key={seat.role} className={`civ-seat civ-seat--${seat.role}`}>
                  <header>{seat.title}</header>
                  <p>{voice?.text || seat.brief}</p>
                </article>
              );
            })}
          </div>
        </div>
      ) : (
        <p className="battle-board-muted civ-cabinet-hint">
          Выберите страну на карте — увидите структуру власти.
        </p>
      )}
    </section>
  );
}

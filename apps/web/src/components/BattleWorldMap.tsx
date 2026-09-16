import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";

import {
  MAP_ZONES,
  clampMapPoint,
  defaultTokenPosition,
  driftTowardWorld,
  truncateCaption,
  zonePowerScale,
  type MapPoint,
  type MapZoneId,
} from "../battle/mapLayout";
import { loadMapPositions, saveMapPositions } from "../battle/mapPersist";
import type { AgentPersona } from "../battle/types";

type TokenState = {
  id: string;
  name: string;
  style: string;
  enabled: boolean;
  pos: MapPoint;
  skipped?: boolean;
};

export type MapAgentCaption = {
  agentId: string;
  text: string;
  phase: string;
  skipped?: boolean;
};

type Props = {
  cast: AgentPersona[];
  running: boolean;
  focusAgentId: string | null;
  selectedAgentId: string | null;
  phase: string | null;
  round: number | null;
  maxRounds: number;
  lastDelta: string;
  skippedIds: Set<string>;
  scores: Record<string, number>;
  captions: MapAgentCaption[];
  stability: number;
  panic: number;
  techLead: Record<string, number>;
  redLine?: boolean;
  onSelectAgent?: (agentId: string) => void;
};

const STYLE_GLYPH: Record<string, string> = {
  hawk: "▲",
  dove: "◇",
  archivist: "▣",
  chaos: "✱",
  engineer: "⬡",
  skeptic: "◎",
  broker: "✦",
};

const FACTION_ZONES: MapZoneId[] = ["atlantic", "pacific", "neutral"];

function buildTokens(cast: AgentPersona[], saved: Record<string, MapPoint>): TokenState[] {
  const enabled = cast.filter((c) => c.enabled);
  return enabled.map((agent, index) => ({
    id: agent.id,
    name: agent.name,
    style: agent.style,
    enabled: agent.enabled,
    pos:
      saved[agent.id] ??
      defaultTokenPosition(agent.id, agent.style, index, enabled.length),
  }));
}

function phaseLabel(phase: string | null): string {
  if (!phase) return "";
  const map: Record<string, string> = {
    brief: "бриф",
    propose: "ходы",
    rebut: "ответ",
    verdict: "вердикт",
  };
  return map[phase] || phase;
}

export function BattleWorldMap({
  cast,
  running,
  focusAgentId,
  selectedAgentId,
  phase,
  round,
  maxRounds,
  lastDelta,
  skippedIds,
  scores,
  captions,
  stability,
  panic,
  techLead,
  redLine = false,
  onSelectAgent,
}: Props) {
  const [tokens, setTokens] = useState<TokenState[]>(() => buildTokens(cast, loadMapPositions()));
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragMoved, setDragMoved] = useState(false);
  const [tickFlash, setTickFlash] = useState(false);
  const boardRef = useRef<HTMLDivElement>(null);
  const persistTimer = useRef<number | null>(null);
  const prevTech = useRef(JSON.stringify(techLead));

  useEffect(() => {
    setTokens((prev) => {
      const saved = Object.fromEntries(prev.map((t) => [t.id, t.pos]));
      const merged = { ...loadMapPositions(), ...saved };
      return buildTokens(cast, merged);
    });
  }, [cast]);

  useEffect(() => {
    setTokens((prev) => prev.map((t) => ({ ...t, skipped: skippedIds.has(t.id) })));
  }, [skippedIds]);

  // World-tick flash when tech_lead or verdict phase shifts.
  useEffect(() => {
    const key = JSON.stringify(techLead);
    if (key !== prevTech.current || phase === "verdict") {
      prevTech.current = key;
      setTickFlash(true);
      const t = window.setTimeout(() => setTickFlash(false), 900);
      return () => window.clearTimeout(t);
    }
  }, [techLead, phase]);

  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => {
      setTokens((prev) =>
        prev.map((t) => {
          if (t.skipped || t.id === focusAgentId || t.id === dragId) return t;
          return { ...t, pos: driftTowardWorld(t.pos, techLead, panic, stability) };
        }),
      );
    }, 900);
    return () => window.clearInterval(id);
  }, [running, techLead, panic, stability, focusAgentId, dragId]);

  useEffect(() => {
    if (persistTimer.current) window.clearTimeout(persistTimer.current);
    persistTimer.current = window.setTimeout(() => {
      const map: Record<string, MapPoint> = {};
      for (const t of tokens) map[t.id] = t.pos;
      saveMapPositions(map);
    }, 280);
    return () => {
      if (persistTimer.current) window.clearTimeout(persistTimer.current);
    };
  }, [tokens]);

  const captionById = useMemo(() => {
    const map = new Map<string, MapAgentCaption>();
    for (const c of captions) map.set(c.agentId, c);
    return map;
  }, [captions]);

  const focusCaption = focusAgentId ? captionById.get(focusAgentId) : undefined;

  const rebutLinks = useMemo(() => {
    if (phase !== "rebut" || !focusAgentId) return [] as { from: MapPoint; to: MapPoint }[];
    const from = tokens.find((t) => t.id === focusAgentId);
    if (!from || from.skipped) return [];
    return tokens
      .filter((t) => t.id !== focusAgentId && !t.skipped && captionById.has(t.id))
      .map((t) => ({ from: from.pos, to: t.pos }));
  }, [phase, focusAgentId, tokens, captionById]);

  const maxScore = useMemo(() => {
    const vals = Object.values(scores);
    return vals.length ? Math.max(...vals, 1) : 1;
  }, [scores]);

  const clientToPct = (clientX: number, clientY: number): MapPoint | null => {
    const el = boardRef.current;
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;
    return clampMapPoint({
      x: ((clientX - rect.left) / rect.width) * 100,
      y: ((clientY - rect.top) / rect.height) * 100,
    });
  };

  const onTokenPointerDown = (id: string, e: ReactPointerEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragId(id);
    setDragMoved(false);
  };

  const onTokenPointerMove = (e: ReactPointerEvent<HTMLButtonElement>) => {
    if (!dragId) return;
    const next = clientToPct(e.clientX, e.clientY);
    if (!next) return;
    setDragMoved(true);
    setTokens((prev) => prev.map((t) => (t.id === dragId ? { ...t, pos: next } : t)));
  };

  const onTokenPointerUp = (id: string, e: ReactPointerEvent<HTMLButtonElement>) => {
    if (dragId) {
      try {
        e.currentTarget.releasePointerCapture(e.pointerId);
      } catch {
        /* already released */
      }
    }
    const wasDrag = dragMoved;
    setDragId(null);
    setDragMoved(false);
    if (!wasDrag) onSelectAgent?.(id);
  };

  const storm = Math.min(1, Math.max(0, panic / 100));
  const calm = Math.min(1, Math.max(0, stability / 100));
  const atlanticScale = zonePowerScale(Number(techLead.atlantic ?? 50));
  const pacificScale = zonePowerScale(Number(techLead.pacific ?? 50));
  const neutralScale = zonePowerScale(Number(techLead.neutral ?? 50));

  const boardClass = [
    "battle-world-board",
    running ? "battle-world-board--live" : "",
    phase ? `battle-world-board--${phase}` : "",
    redLine ? "battle-world-board--red" : "",
    tickFlash ? "battle-world-board--tick" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const focusName = tokens.find((t) => t.id === focusAgentId)?.name || null;
  const focusLine = focusCaption?.text
    ? truncateCaption(focusCaption.text.replace(/^ХОД:\s*/i, ""), 110)
    : null;

  return (
    <section className="battle-world" aria-label="Карта арены">
      <div className="battle-world-head">
        <div>
          <h3 className="battle-section-title">Карта мира</h3>
          <p className="battle-world-hint">
            Слева блоки мира, справа фишки ходов. Цифры на зонах = tech_lead. Кликни фишку → лента.
          </p>
        </div>
        <div className="battle-world-meta" aria-live="polite">
          {running ? (
            <span className="battle-world-live">
              LIVE · шаг {round ?? "—"}/{maxRounds}
              {phase ? ` · ${phaseLabel(phase)}` : ""}
            </span>
          ) : (
            <span className="battle-board-muted">ожидание запуска · {maxRounds} шагов</span>
          )}
        </div>
      </div>

      <div className="battle-world-ticker" aria-live="polite">
        <div>
          <strong>Сейчас:</strong>{" "}
          {focusName ? focusName : running ? "ждём ход…" : "—"}
          {focusLine ? ` — ${focusLine}` : ""}
        </div>
        <div>
          <strong>Мир Δ:</strong> {lastDelta || "пока нет изменений"}
        </div>
      </div>

      <div className="battle-world-factions" aria-label="Баланс блоков">
        {FACTION_ZONES.map((zid) => {
          const score = Math.round(Number(techLead[zid] ?? 50));
          return (
            <div key={zid} className={`battle-world-faction battle-world-faction--${zid}`}>
              <span>{MAP_ZONES[zid].short}</span>
              <strong>{score}</strong>
              <i style={{ width: `${Math.max(8, Math.min(100, score))}%` }} />
            </div>
          );
        })}
        <div className="battle-world-faction battle-world-faction--meters">
          <span>Стаб. {Math.round(stability)}</span>
          <span>Паника {Math.round(panic)}</span>
        </div>
      </div>

      <div
        ref={boardRef}
        className={boardClass}
        style={
          {
            "--storm": String(storm),
            "--calm": String(calm),
            "--atl-scale": String(atlanticScale),
            "--pac-scale": String(pacificScale),
            "--neu-scale": String(neutralScale),
          } as CSSProperties
        }
      >
        <svg
          className="battle-world-terrain"
          viewBox="0 0 100 70"
          preserveAspectRatio="none"
          aria-hidden
        >
          <defs>
            <linearGradient id="bw-ocean" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#1a4a5c" />
              <stop offset="45%" stopColor="#236b6e" />
              <stop offset="100%" stopColor="#1e5a4a" />
            </linearGradient>
            <radialGradient id="bw-fog" cx="50%" cy="40%" r="70%">
              <stop offset="0%" stopColor="rgba(255,255,255,0)" />
              <stop offset="100%" stopColor="rgba(8,20,24,0.35)" />
            </radialGradient>
            <filter id="bw-soft">
              <feGaussianBlur stdDeviation="0.4" />
            </filter>
          </defs>
          <rect width="100" height="70" fill="url(#bw-ocean)" />
          <g
            className="battle-world-land-wrap"
            transform={`translate(22 36) scale(${atlanticScale}) translate(-22 -36)`}
          >
            <path
              className="battle-world-land battle-world-land--atlantic"
              d="M8 28 C14 18, 28 16, 34 26 C38 34, 30 48, 20 50 C10 52, 4 40, 8 28 Z"
              filter="url(#bw-soft)"
            />
          </g>
          <g
            className="battle-world-land-wrap"
            transform={`translate(80 32) scale(${pacificScale}) translate(-80 -32)`}
          >
            <path
              className="battle-world-land battle-world-land--pacific"
              d="M66 18 C78 12, 92 16, 94 28 C96 40, 86 52, 74 50 C64 48, 58 30, 66 18 Z"
              filter="url(#bw-soft)"
            />
          </g>
          <g
            className="battle-world-land-wrap"
            transform={`translate(46 55) scale(${neutralScale}) translate(-46 -55)`}
          >
            <path
              className="battle-world-land battle-world-land--neutral"
              d="M30 48 C40 44, 55 46, 62 54 C58 62, 42 66, 32 60 C26 56, 26 50, 30 48 Z"
              filter="url(#bw-soft)"
            />
          </g>
          <ellipse
            className="battle-world-land battle-world-land--summit"
            cx="52"
            cy="34"
            rx="5.5"
            ry="3.8"
          />
          <path className="battle-world-route" d="M24 36 C36 30, 44 32, 52 34" fill="none" />
          <path className="battle-world-route" d="M52 34 C62 30, 70 32, 78 34" fill="none" />
          <path className="battle-world-route" d="M52 34 C50 44, 48 50, 46 56" fill="none" />

          {rebutLinks.map((link, i) => (
            <line
              key={`rebut-${i}`}
              className="battle-world-rebut"
              x1={link.from.x}
              y1={(link.from.y / 100) * 70}
              x2={link.to.x}
              y2={(link.to.y / 100) * 70}
            />
          ))}

          <rect width="100" height="70" fill="url(#bw-fog)" className="battle-world-fog" />
        </svg>

        <div className="battle-world-weather" aria-hidden />
        <div className="battle-world-scan" aria-hidden />
        {redLine ? <div className="battle-world-redflash" aria-hidden /> : null}

        {FACTION_ZONES.map((zid) => {
          const z = MAP_ZONES[zid];
          const score = Number(techLead[zid] ?? 50);
          const scale = zonePowerScale(score);
          return (
            <div
              key={zid}
              className={`battle-world-aura battle-world-aura--${zid}`}
              style={{
                left: `${z.center.x}%`,
                top: `${z.center.y}%`,
                transform: `translate(-50%, -50%) scale(${scale})`,
                opacity: 0.25 + (score / 100) * 0.45,
              }}
              aria-hidden
            />
          );
        })}

        {(Object.keys(MAP_ZONES) as MapZoneId[]).map((zid) => {
          const z = MAP_ZONES[zid];
          const score =
            zid === "summit" ? null : Math.round(Number(techLead[zid] ?? 50));
          return (
            <div
              key={zid}
              className={`battle-world-zone battle-world-zone--${zid}`}
              style={{ left: `${z.center.x}%`, top: `${z.center.y}%` }}
            >
              <span>
                {z.short}
                {score != null ? ` · ${score}` : ""}
              </span>
            </div>
          );
        })}

        {focusCaption && !focusCaption.skipped ? (
          <div
            className="battle-world-speech"
            style={{
              left: `${tokens.find((t) => t.id === focusAgentId)?.pos.x ?? 50}%`,
              top: `${(tokens.find((t) => t.id === focusAgentId)?.pos.y ?? 40) - 8}%`,
            }}
          >
            {truncateCaption(focusCaption.text, 90)}
          </div>
        ) : null}

        {tokens.map((token) => {
          const active = focusAgentId === token.id;
          const selected = selectedAgentId === token.id;
          const glyph = STYLE_GLYPH[token.style] || "●";
          const pts = scores[token.id];
          const ring = pts != null ? Math.max(0.2, Math.min(1, pts / maxScore)) : 0;
          const cap = captionById.get(token.id);
          return (
            <button
              key={token.id}
              type="button"
              className={[
                "battle-token",
                `battle-token--${token.style}`,
                active ? "battle-token--active" : "",
                selected ? "battle-token--selected" : "",
                token.skipped ? "battle-token--skip" : "",
                dragId === token.id ? "battle-token--drag" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              style={
                {
                  left: `${token.pos.x}%`,
                  top: `${token.pos.y}%`,
                  "--score-ring": String(ring),
                } as CSSProperties
              }
              title={cap && !cap.skipped ? truncateCaption(cap.text, 140) : token.name}
              aria-label={`${token.name}${active ? ", активен" : ""}${token.skipped ? ", пропуск" : ""}${pts != null ? `, ${pts.toFixed(1)} очков` : ""}`}
              aria-grabbed={dragId === token.id}
              onPointerDown={(e) => onTokenPointerDown(token.id, e)}
              onPointerMove={onTokenPointerMove}
              onPointerUp={(e) => onTokenPointerUp(token.id, e)}
              onPointerCancel={(e) => onTokenPointerUp(token.id, e)}
            >
              {pts != null && !token.skipped ? (
                <span className="battle-token-score" aria-hidden>
                  {pts.toFixed(0)}
                </span>
              ) : null}
              <span className="battle-token-glyph" aria-hidden>
                {token.skipped ? "✕" : glyph}
              </span>
              <span className="battle-token-name">{token.name}</span>
              {active ? <span className="battle-token-pulse" aria-hidden /> : null}
            </button>
          );
        })}

        <div className="battle-world-legend" aria-hidden>
          <span>стаб. {Math.round(stability)}</span>
          <span>паника {Math.round(panic)}</span>
          {phase ? <span>{phaseLabel(phase)}</span> : null}
        </div>
      </div>
    </section>
  );
}

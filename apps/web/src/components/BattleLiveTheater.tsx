import { useMemo } from "react";

import type { CabinetVoice } from "../battle/cabinet";
import type { ConflictLivePatch, ConflictView } from "../battle/conflictBridge";
import { MEANS_META, type BattleMeans } from "../battle/means";
import type { AgentPersona } from "../battle/types";

export type LiveView = "civ" | ConflictView;

type Bloc = {
  id: "ATL" | "PAC" | "NEU";
  faction: string;
  name: string;
  x: number;
  y: number;
  color: string;
};

const BLOCS: Bloc[] = [
  { id: "ATL", faction: "atlantic", name: "Atlantic", x: 248, y: 228, color: "#3d7ea6" },
  { id: "PAC", faction: "pacific", name: "Pacific", x: 412, y: 206, color: "#2f8f6b" },
  { id: "NEU", faction: "neutral", name: "Neutral", x: 328, y: 312, color: "#c4a35a" },
];

type Arc = { from: string; to: string; kind: string };

type Props = {
  view: LiveView;
  patch: ConflictLivePatch;
  arcs: Arc[];
  orders: NonNullable<ConflictLivePatch["lastOrders"]>;
  running: boolean;
  cast: AgentPersona[];
};

function curve(a: { x: number; y: number }, b: { x: number; y: number }): string {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2 - 42 - Math.abs(a.x - b.x) * 0.08;
  return `M${a.x} ${a.y} Q ${mx} ${my} ${b.x} ${b.y}`;
}

function blocOf(id: string): Bloc | undefined {
  return BLOCS.find((b) => b.id === id);
}

function Hud({ patch }: { patch: ConflictLivePatch }) {
  return (
    <div className="live-hud" aria-live="polite">
      <span>
        ход {patch.turn ?? 0} · {patch.escalation}
      </span>
      <span>oil ${patch.oil ?? "—"}</span>
      <span>shipping {Math.round((patch.shippingRisk ?? 0) * 100)}%</span>
      <span>sanctions {Math.round((patch.sanctionsPressure ?? 0) * 100)}%</span>
    </div>
  );
}

function ArcLayer({
  arcs,
  fxKey,
  animate,
}: {
  arcs: Arc[];
  fxKey: string;
  animate: boolean;
}) {
  return (
    <g>
      {arcs.map((arc, i) => {
        const from = blocOf(arc.from);
        const to = blocOf(arc.to);
        if (!from || !to) return null;
        const id = `live-arc-${i}-${arc.from}-${arc.to}`;
        return (
          <g key={id}>
            <path
              id={id}
              d={curve(from, to)}
              className={`live-arc live-arc--${arc.kind}`}
              pathLength={100}
            />
            {animate && arc.kind === "war" ? (
              <polygon
                key={`${fxKey}-${id}`}
                className="live-missile"
                points="0,-3 11,0 0,3"
              >
                <animateMotion dur="1.4s" rotate="auto" repeatCount="1" fill="freeze">
                  <mpath href={`#${id}`} />
                </animateMotion>
              </polygon>
            ) : null}
          </g>
        );
      })}
    </g>
  );
}

function Cities({
  patch,
  actor,
}: {
  patch: ConflictLivePatch;
  actor: string | null;
}) {
  return (
    <g>
      {BLOCS.map((b) => {
        const support = Number(patch.warSupport?.[b.id] ?? 0.45);
        const r = 7 + support * 12;
        const active = actor === b.id;
        return (
          <g key={b.id} transform={`translate(${b.x} ${b.y})`}>
            {active ? (
              <circle className="live-city-pulse" r={r + 10} stroke={b.color} />
            ) : null}
            <circle r={r} fill={b.color} opacity={0.35 + support * 0.5} />
            <circle r={3} fill="#fff" />
            <text x={12} y={4} className="live-label">
              {b.name} {Math.round(support * 100)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

function SidePanel({
  patch,
  orders,
  cast,
}: {
  patch: ConflictLivePatch;
  orders: NonNullable<ConflictLivePatch["lastOrders"]>;
  cast: AgentPersona[];
}) {
  const models = Object.fromEntries(
    cast.filter((c) => c.enabled).map((c) => [c.id, c.preferred_model || "auto"]),
  );
  return (
    <aside className="live-side">
      <h3>Кабинеты / модели</h3>
      <ul>
        {cast
          .filter((c) => c.enabled)
          .map((c) => (
            <li key={c.id}>
              <strong>{c.name}</strong>
              <code>{models[c.id]}</code>
            </li>
          ))}
      </ul>
      <h3>Ходы</h3>
      {orders.length === 0 ? (
        <p className="battle-board-muted">Ждём ход битвы — не demo.</p>
      ) : (
        <ol className="live-orders">
          {orders.slice(-8).map((o, i) => (
            <li key={`${o.actor}-${o.action}-${i}`}>
              {o.actor} → {o.action}
              {o.target ? ` @${o.target}` : ""} {o.rationale ? `· ${o.rationale}` : ""}
            </li>
          ))}
        </ol>
      )}
      {patch.briefingsShown ? (
        <>
          <h3>Брифинг кабинета</h3>
          {Object.entries(patch.briefingsShown).map(([id, text]) => (
            <p key={id} className="live-brief">
              <strong>{id}:</strong> {text}
            </p>
          ))}
        </>
      ) : null}
      <p className="live-narrator">{patch.narrator}</p>
    </aside>
  );
}

function Globe({
  patch,
  arcs,
  fxKey,
}: {
  patch: ConflictLivePatch;
  arcs: Arc[];
  fxKey: string;
}) {
  const actor = patch.lastOrders?.[0]?.actor ?? null;
  const esc = patch.escalation || "peacetime";
  return (
    <svg className={`live-svg live-svg--${esc}`} viewBox="0 0 640 420" role="img" aria-label="Live globe">
      <rect width="640" height="420" className="live-void" />
      <circle cx="320" cy="210" r="148" className="live-ocean" />
      <circle cx="320" cy="210" r="148" className="live-rim" fill="none" />
      <path
        className="live-land"
        d="M210 160 C270 120, 340 128, 360 175 C385 215, 350 250, 300 258 C250 268, 210 230, 210 190 Z"
      />
      <path
        className="live-land2"
        d="M360 168 C430 140, 500 160, 520 210 C535 250, 500 290, 450 300 C400 312, 350 270, 348 220 Z"
      />
      <ArcLayer arcs={arcs} fxKey={fxKey} animate={Boolean(patch.animate)} />
      <Cities patch={patch} actor={actor} />
    </svg>
  );
}

function Planet({
  patch,
  arcs,
  fxKey,
}: {
  patch: ConflictLivePatch;
  arcs: Arc[];
  fxKey: string;
}) {
  const heat = Math.min(1, (patch.shippingRisk ?? 0.2) + (patch.escalation === "launch_ready" ? 0.4 : 0));
  return (
    <svg className="live-svg live-svg--planet" viewBox="0 0 640 420" role="img" aria-label="Live planet">
      <rect width="640" height="420" fill="#0c1220" />
      {Array.from({ length: 28 }, (_, i) => (
        <circle
          key={i}
          cx={20 + ((i * 97) % 640)}
          cy={12 + ((i * 53) % 400)}
          r={i % 4 === 0 ? 1.4 : 0.7}
          fill="#dce7ff"
          opacity={0.45}
        />
      ))}
      <circle cx="320" cy="210" r="132" fill={`rgb(${40 + heat * 80}, ${50 - heat * 20}, ${70})`} />
      <ellipse cx="280" cy="170" rx="90" ry="110" fill="#000" opacity={0.18} />
      <path
        fill="#2f6b48"
        opacity={0.85}
        d="M250 150 C300 120, 360 140, 380 180 C390 210, 350 240, 300 245 C260 248, 235 210, 250 170 Z"
      />
      <path
        fill="#3a7a4a"
        opacity={0.8}
        d="M360 190 C410 170, 470 190, 490 230 C500 260, 460 290, 410 292 C370 294, 345 250, 360 210 Z"
      />
      <ArcLayer arcs={arcs} fxKey={fxKey} animate={Boolean(patch.animate || patch.fx === "strike")} />
      <Cities patch={patch} actor={patch.lastOrders?.[0]?.actor ?? null} />
    </svg>
  );
}

function Strategy({
  patch,
  arcs,
  fxKey,
}: {
  patch: ConflictLivePatch;
  arcs: Arc[];
  fxKey: string;
}) {
  return (
    <svg className="live-svg live-svg--strategy" viewBox="0 0 640 420" role="img" aria-label="Strategy board">
      <rect width="640" height="420" fill="#e8d7b4" />
      <path fill="#c9b48a" d="M40 60 H600 V360 H40 Z" />
      <ellipse cx="210" cy="200" rx="90" ry="70" fill="#3d7ea6" opacity={0.55} />
      <ellipse cx="430" cy="175" rx="95" ry="68" fill="#2f8f6b" opacity={0.55} />
      <ellipse cx="330" cy="300" rx="80" ry="52" fill="#c4a35a" opacity={0.7} />
      <text x="210" y="205" textAnchor="middle" className="live-ink">
        ATL {Math.round((patch.warSupport?.ATL ?? 0) * 100)}
      </text>
      <text x="430" y="180" textAnchor="middle" className="live-ink">
        PAC {Math.round((patch.warSupport?.PAC ?? 0) * 100)}
      </text>
      <text x="330" y="305" textAnchor="middle" className="live-ink">
        NEU {Math.round((patch.warSupport?.NEU ?? 0) * 100)}
      </text>
      <ArcLayer arcs={arcs} fxKey={fxKey} animate={Boolean(patch.animate)} />
    </svg>
  );
}

function ArcsBoard({
  patch,
  arcs,
  fxKey,
}: {
  patch: ConflictLivePatch;
  arcs: Arc[];
  fxKey: string;
}) {
  return (
    <svg className="live-svg" viewBox="0 0 640 420" role="img" aria-label="Conflict arcs">
      <rect width="640" height="420" fill="#121826" />
      <text x="24" y="28" className="live-meta">
        theaters · {arcs.length} links · {patch.escalation}
      </text>
      <ArcLayer arcs={arcs} fxKey={fxKey} animate />
      <Cities patch={patch} actor={patch.lastOrders?.[0]?.actor ?? null} />
    </svg>
  );
}

export function BattleLiveTheater({ view, patch, arcs, orders, running, cast }: Props) {
  const fxKey = `${patch.turn}-${patch.fx}-${patch.lastOrders?.[0]?.action ?? ""}`;
  const mergedArcs = useMemo(() => {
    const seen = new Set<string>();
    const out: Arc[] = [];
    for (const a of arcs) {
      const k = `${a.from}:${a.to}:${a.kind}`;
      if (seen.has(k)) continue;
      seen.add(k);
      out.push(a);
    }
    return out;
  }, [arcs]);

  if (view === "civ") return null;

  return (
    <section className={`live-theater${running ? " is-live" : ""}`} aria-label="Live conflict views">
      <Hud patch={patch} />
      <div className="live-grid">
        {view === "llm" ? <Globe patch={patch} arcs={mergedArcs} fxKey={fxKey} /> : null}
        {view === "planet" ? <Planet patch={patch} arcs={mergedArcs} fxKey={fxKey} /> : null}
        {view === "parchment" ? <Strategy patch={patch} arcs={mergedArcs} fxKey={fxKey} /> : null}
        {view === "arcs" ? <ArcsBoard patch={patch} arcs={mergedArcs} fxKey={fxKey} /> : null}
        <SidePanel patch={patch} orders={orders} cast={cast} />
      </div>
    </section>
  );
}

export function meansChip(means: BattleMeans | null): string {
  if (!means) return "";
  return `${MEANS_META[means].icon} ${MEANS_META[means].label}`;
}

export type { CabinetVoice };

/**
 * Map AIChallenge Agent Battle live meters → conflict-emulation LLM-board worldState.
 * Practices: viz = f(worldState); structured action codes only.
 */

import type { BattleMeans } from "./means";
import type { CabinetVoice } from "./cabinet";

export type ConflictView = "llm" | "planet" | "parchment" | "arcs";

export type ConflictActorId = "ATL" | "PAC" | "NEU";

export type ConflictLivePatch = {
  reset?: boolean;
  turn?: number;
  escalation?: string;
  oil?: number;
  shippingRisk?: number;
  sanctionsPressure?: number;
  warSupport?: Partial<Record<ConflictActorId, number>>;
  arcs?: { from: string; to: string; kind: string }[];
  lastOrders?: {
    actor: string;
    action: string;
    target?: string;
    rationale?: string;
  }[];
  briefingsShown?: Record<string, string>;
  narrator?: string;
  animate?: boolean;
};

const FACTION_TO_ACTOR: Record<string, ConflictActorId> = {
  atlantic: "ATL",
  pacific: "PAC",
  neutral: "NEU",
};

const MEANS_TO_ACTION: Record<BattleMeans, string> = {
  diplomacy: "DIPLOMATIZE",
  sanctions: "SANCTION",
  cyber: "STRIKE",
  mobilize: "FORTIFY",
  deterrence: "FORTIFY",
  strike: "STRIKE",
};

const MEANS_TO_ARC: Record<BattleMeans, string> = {
  diplomacy: "ally",
  sanctions: "sanction",
  cyber: "war",
  mobilize: "trade",
  deterrence: "ally",
  strike: "war",
};

function ladder(escalation: number, panic: number, means: BattleMeans | null): string {
  if (means === "strike" || escalation >= 4 || panic >= 80) return "launch_ready";
  if (escalation >= 3 || panic >= 65) return "dispersal";
  if (escalation >= 2 || means === "deterrence" || means === "cyber") return "elevated";
  if (escalation >= 1 || panic >= 45) return "tense";
  return "peacetime";
}

function otherTargets(actor: ConflictActorId): ConflictActorId[] {
  return (["ATL", "PAC", "NEU"] as ConflictActorId[]).filter((id) => id !== actor);
}

export function battleToConflictPatch(args: {
  round: number | null;
  stability: number;
  panic: number;
  techLead: Record<string, number>;
  escalation: number;
  means: BattleMeans | null;
  meansActor: string | null;
  lastDelta: string;
  cabinet: CabinetVoice[];
  cabinetNationId: string | null;
}): ConflictLivePatch {
  const {
    round,
    stability,
    panic,
    techLead,
    escalation,
    means,
    meansActor,
    lastDelta,
    cabinet,
    cabinetNationId,
  } = args;

  const actor = meansActor ? FACTION_TO_ACTOR[meansActor] : null;
  const targets = actor ? otherTargets(actor) : [];
  const primaryTarget = targets[0];

  const arcs: ConflictLivePatch["arcs"] = [];
  const lastOrders: ConflictLivePatch["lastOrders"] = [];

  if (actor && means) {
    const action = MEANS_TO_ACTION[means];
    const kind = MEANS_TO_ARC[means];
    const target = means === "mobilize" || means === "deterrence" ? actor : primaryTarget;
    lastOrders.push({
      actor,
      action,
      target: target || actor,
      rationale: lastDelta || means,
    });
    if (target && target !== actor) {
      arcs.push({ from: actor, to: target, kind });
    } else if (means === "diplomacy" && primaryTarget) {
      arcs.push({ from: actor, to: primaryTarget, kind: "ally" });
    }
  }

  const warSupport: ConflictLivePatch["warSupport"] = {
    ATL: Math.max(0.05, Math.min(1, Number(techLead.atlantic ?? 50) / 100)),
    PAC: Math.max(0.05, Math.min(1, Number(techLead.pacific ?? 50) / 100)),
    NEU: Math.max(0.05, Math.min(1, Number(techLead.neutral ?? 50) / 100)),
  };

  const briefingsShown: Record<string, string> = {};
  const briefNation = cabinetNationId ? FACTION_TO_ACTOR[cabinetNationId] : actor;
  if (briefNation && cabinet.length) {
    briefingsShown[briefNation] = cabinet.map((v) => `${v.title}: ${v.text}`).join(" · ");
  }

  const oil = Math.round(70 + panic * 0.35 - stability * 0.08);
  const shippingRisk = Math.max(0.05, Math.min(1, panic / 100 + escalation * 0.08));
  const sanctionsPressure = Math.max(
    0.1,
    Math.min(1, (100 - stability) / 120 + (means === "sanctions" ? 0.15 : 0)),
  );

  return {
    turn: round ?? 0,
    escalation: ladder(escalation, panic, means),
    oil,
    shippingRisk,
    sanctionsPressure,
    warSupport,
    arcs,
    lastOrders,
    briefingsShown: Object.keys(briefingsShown).length ? briefingsShown : undefined,
    narrator:
      `Battle bridge · round ${round ?? 0} · stab ${Math.round(stability)} · panic ${Math.round(panic)}` +
      (lastDelta ? ` · Δ ${lastDelta}` : "") +
      (means && actor ? ` · ${actor}:${means}` : ""),
    animate: means === "strike" || means === "cyber" || means === "deterrence",
  };
}

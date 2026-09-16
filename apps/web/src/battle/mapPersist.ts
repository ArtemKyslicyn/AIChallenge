/** Persist draggable token positions for the battle open-world map. */

import type { MapPoint } from "./mapLayout";

const KEY = "aichallenge.battle_map.v1";

export type BattleMapPositions = Record<string, MapPoint>;

export function loadMapPositions(): BattleMapPositions {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    const out: BattleMapPositions = {};
    for (const [id, val] of Object.entries(parsed as Record<string, unknown>)) {
      if (!val || typeof val !== "object") continue;
      const pt = val as { x?: unknown; y?: unknown };
      if (typeof pt.x === "number" && typeof pt.y === "number") {
        out[id] = { x: pt.x, y: pt.y };
      }
    }
    return out;
  } catch {
    return {};
  }
}

export function saveMapPositions(positions: BattleMapPositions): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(positions));
  } catch {
    /* ignore quota */
  }
}

export function clearMapPositions(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

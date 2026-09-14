/** localStorage load/save for battle arena. */

import { createDefaultArena } from "./defaultArena";
import type { ArenaDoc } from "./types";

const KEY = "aichallenge.battle_arena.v1";

function isArena(raw: unknown): raw is ArenaDoc {
  if (!raw || typeof raw !== "object") return false;
  const doc = raw as ArenaDoc;
  return (
    doc.version === 1 &&
    typeof doc.id === "string" &&
    typeof doc.name === "string" &&
    !!doc.world &&
    !!doc.inputs &&
    Array.isArray(doc.cast) &&
    !!doc.rules
  );
}

export function loadArena(): ArenaDoc {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return createDefaultArena();
    const parsed: unknown = JSON.parse(raw);
    if (isArena(parsed) && parsed.cast.length > 0) return parsed;
  } catch {
    /* ignore */
  }
  return createDefaultArena();
}

export function saveArena(doc: ArenaDoc): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(doc));
  } catch {
    /* ignore quota */
  }
}

export function resetDefaultArena(): ArenaDoc {
  const fresh = createDefaultArena();
  saveArena(fresh);
  return fresh;
}

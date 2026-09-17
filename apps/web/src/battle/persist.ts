/** localStorage load/save for battle arena. */

import { createDefaultArena } from "./defaultArena";
import type { ArenaDoc } from "./types";

const KEY = "aichallenge.battle_arena.v2";
const LEGACY_KEY = "aichallenge.battle_arena.v1";

function isArena(raw: unknown): raw is ArenaDoc {
  if (!raw || typeof raw !== "object") return false;
  const doc = raw as ArenaDoc;
  return (
    (doc.version === 1 || doc.version === 2) &&
    typeof doc.id === "string" &&
    typeof doc.name === "string" &&
    !!doc.world &&
    !!doc.inputs &&
    Array.isArray(doc.cast) &&
    !!doc.rules
  );
}

function migrateArena(doc: ArenaDoc): ArenaDoc {
  const hasNations = doc.cast.some((c) => c.id === "atlantic") && doc.cast.length === 3;
  if (!hasNations) return createDefaultArena();
  return {
    ...doc,
    version: 1,
    rules: {
      ...doc.rules,
      max_rounds: Math.max(12, Number(doc.rules.max_rounds) || 12),
      skip_rebut: true,
      stop_on_red_line: false,
    },
  };
}

export function loadArena(): ArenaDoc {
  try {
    const raw = localStorage.getItem(KEY) || localStorage.getItem(LEGACY_KEY);
    if (!raw) return createDefaultArena();
    const parsed: unknown = JSON.parse(raw);
    if (isArena(parsed) && parsed.cast.length > 0) {
      const migrated = migrateArena(parsed);
      saveArena(migrated);
      return migrated;
    }
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

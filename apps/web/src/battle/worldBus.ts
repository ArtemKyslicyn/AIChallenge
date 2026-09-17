/**
 * Shared battle world bus — WarAgent / multi-agent-simulation-engine practice:
 * one worldState checkpoint, all viz = f(worldState).
 */

import type { ConflictLivePatch } from "./conflictBridge";

const KEY = "aichallenge.battle_world_bus.v1";
const CHANNEL = "aichallenge-battle-world";

export type BattleWorldSnapshot = {
  version: 1;
  updated_at: string;
  seq: number;
  patch: ConflictLivePatch;
};

type Listener = (snap: BattleWorldSnapshot) => void;

let seq = 0;
let latest: BattleWorldSnapshot | null = null;
const listeners = new Set<Listener>();
let channel: BroadcastChannel | null = null;

function getChannel(): BroadcastChannel | null {
  if (typeof BroadcastChannel === "undefined") return null;
  if (!channel) {
    channel = new BroadcastChannel(CHANNEL);
    channel.onmessage = (ev) => {
      const snap = ev.data as BattleWorldSnapshot;
      if (!snap || snap.version !== 1) return;
      latest = snap;
      seq = Math.max(seq, snap.seq);
      listeners.forEach((fn) => fn(snap));
    };
  }
  return channel;
}

export function loadWorldBus(): BattleWorldSnapshot | null {
  if (latest) return latest;
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as BattleWorldSnapshot;
    if (parsed?.version === 1 && parsed.patch) {
      latest = parsed;
      seq = parsed.seq || 0;
      return parsed;
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function publishWorldBus(patch: ConflictLivePatch): BattleWorldSnapshot {
  seq += 1;
  const snap: BattleWorldSnapshot = {
    version: 1,
    updated_at: new Date().toISOString(),
    seq,
    patch,
  };
  latest = snap;
  try {
    localStorage.setItem(KEY, JSON.stringify(snap));
  } catch {
    /* ignore */
  }
  try {
    getChannel()?.postMessage(snap);
  } catch {
    /* ignore */
  }
  listeners.forEach((fn) => fn(snap));
  return snap;
}

export function subscribeWorldBus(fn: Listener): () => void {
  listeners.add(fn);
  getChannel();
  const cur = loadWorldBus();
  if (cur) fn(cur);
  return () => listeners.delete(fn);
}

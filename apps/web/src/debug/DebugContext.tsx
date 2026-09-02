import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type DebugKind = "info" | "lab" | "model" | "error" | "http" | "judge";

export interface DebugEvent {
  id: string;
  ts: number;
  kind: DebugKind;
  message: string;
}

interface DebugApi {
  events: DebugEvent[];
  unreadErrors: number;
  push: (kind: DebugKind, message: string) => void;
  clear: () => void;
  markSeen: () => void;
}

const DebugContext = createContext<DebugApi | null>(null);
const MAX_EVENTS = 200;

export function DebugProvider({ children }: { children: ReactNode }) {
  const [events, setEvents] = useState<DebugEvent[]>([]);
  const [seenErrorId, setSeenErrorId] = useState<string | null>(null);

  const push = useCallback((kind: DebugKind, message: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setEvents((prev) => {
      const next = [{ id, ts: Date.now(), kind, message }, ...prev];
      return next.length > MAX_EVENTS ? next.slice(0, MAX_EVENTS) : next;
    });
  }, []);

  const clear = useCallback(() => {
    setEvents([]);
    setSeenErrorId(null);
  }, []);

  const markSeen = useCallback(() => {
    setSeenErrorId(events.find((e) => e.kind === "error")?.id ?? null);
  }, [events]);

  const unreadErrors = useMemo(() => {
    let n = 0;
    for (const e of events) {
      if (e.kind !== "error") continue;
      if (seenErrorId && e.id === seenErrorId) break;
      n += 1;
    }
    return n;
  }, [events, seenErrorId]);

  const value = useMemo(
    () => ({ events, unreadErrors, push, clear, markSeen }),
    [events, unreadErrors, push, clear, markSeen],
  );

  return <DebugContext.Provider value={value}>{children}</DebugContext.Provider>;
}

export function useDebugLog(): DebugApi {
  const ctx = useContext(DebugContext);
  if (!ctx) {
    return {
      events: [],
      unreadErrors: 0,
      push: () => undefined,
      clear: () => undefined,
      markSeen: () => undefined,
    };
  }
  return ctx;
}

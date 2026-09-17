import { useEffect, useRef } from "react";

import type { ConflictLivePatch, ConflictView } from "../battle/conflictBridge";
import { loadWorldBus, subscribeWorldBus } from "../battle/worldBus";

type Props = {
  view: ConflictView;
  livePatch: ConflictLivePatch | null;
  /** When false, host stays mounted but hidden (keeps bridge warm during Civ tab). */
  active?: boolean;
};

/**
 * Always-on iframe host. Stable URL (no hash reload). Queues patches until
 * LLM board script signals ready — fixes lost postMessage race.
 */
export function ConflictEmulationHost({ view, livePatch, active = true }: Props) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const readyRef = useRef(false);
  const patchRef = useRef<ConflictLivePatch | null>(livePatch);
  const viewRef = useRef(view);

  viewRef.current = view;
  patchRef.current = livePatch;

  const post = (payload: Record<string, unknown>) => {
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    try {
      win.postMessage(payload, "*");
    } catch {
      /* ignore */
    }
  };

  const flush = () => {
    post({ type: "aichallenge.conflict.show", view: viewRef.current });
    const patch = patchRef.current || loadWorldBus()?.patch || null;
    if (patch) post({ type: "aichallenge.conflict.live", patch });
  };

  useEffect(() => {
    const onMessage = (ev: MessageEvent) => {
      const data = ev.data;
      if (!data || typeof data !== "object") return;
      if (data.type === "aichallenge.conflict.ready") {
        readyRef.current = true;
        flush();
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  useEffect(() => {
    if (!readyRef.current) return;
    post({ type: "aichallenge.conflict.show", view });
  }, [view]);

  useEffect(() => {
    if (!livePatch) return;
    patchRef.current = livePatch;
    if (readyRef.current) {
      post({ type: "aichallenge.conflict.live", patch: livePatch });
    }
  }, [livePatch]);

  useEffect(() => {
    return subscribeWorldBus((snap) => {
      patchRef.current = snap.patch;
      if (readyRef.current) {
        post({ type: "aichallenge.conflict.live", patch: snap.patch });
      }
    });
  }, []);

  return (
    <div
      className={active ? "conflict-host" : "conflict-host conflict-host--dormant"}
      aria-hidden={!active}
      hidden={!active ? undefined : undefined}
      style={active ? undefined : { position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}
    >
      <iframe
        ref={iframeRef}
        className="conflict-host-frame"
        title="Conflict emulation board"
        src="/conflict/index.html?embed=1"
        onLoad={() => {
          readyRef.current = false;
          post({ type: "aichallenge.conflict.ping" });
          // Retry flush: board may signal ready slightly later
          window.setTimeout(() => post({ type: "aichallenge.conflict.ping" }), 200);
          window.setTimeout(() => post({ type: "aichallenge.conflict.ping" }), 800);
        }}
      />
      {active ? (
        <p className="conflict-host-bridge" aria-live="polite">
          Live bridge · turn {livePatch?.turn ?? "—"} · {livePatch?.escalation ?? "…"} ·{" "}
          {livePatch?.narrator ? livePatch.narrator.slice(0, 120) : "ожидание хода битвы"}
        </p>
      ) : null}
    </div>
  );
}

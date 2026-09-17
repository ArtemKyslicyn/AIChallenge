import { useEffect, useRef } from "react";

import type { ConflictLivePatch, ConflictView } from "../battle/conflictBridge";

type Props = {
  view: ConflictView;
  livePatch: ConflictLivePatch | null;
};

export function ConflictEmulationHost({ view, livePatch }: Props) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const readyRef = useRef(false);

  const post = (payload: Record<string, unknown>) => {
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    try {
      win.postMessage(payload, window.location.origin);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    const onMessage = (ev: MessageEvent) => {
      if (ev.origin !== window.location.origin) return;
      if (ev.data?.type === "aichallenge.conflict.ready") {
        readyRef.current = true;
        post({ type: "aichallenge.conflict.show", view });
        if (livePatch) post({ type: "aichallenge.conflict.live", patch: livePatch });
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [view, livePatch]);

  useEffect(() => {
    post({ type: "aichallenge.conflict.show", view });
  }, [view]);

  useEffect(() => {
    if (!livePatch) return;
    post({ type: "aichallenge.conflict.live", patch: livePatch });
  }, [livePatch]);

  return (
    <div className="conflict-host" aria-label="Conflict emulation views">
      <iframe
        ref={iframeRef}
        className="conflict-host-frame"
        title="Conflict emulation board"
        src={`/conflict/index.html?embed=1#${view}`}
        onLoad={() => {
          readyRef.current = true;
          post({ type: "aichallenge.conflict.show", view });
          if (livePatch) post({ type: "aichallenge.conflict.live", patch: livePatch });
          post({ type: "aichallenge.conflict.ping" });
        }}
      />
    </div>
  );
}

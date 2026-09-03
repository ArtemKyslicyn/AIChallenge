import { useCallback, useEffect, useId, useRef, useState } from "react";

import { useDebugLog, type DebugKind } from "../debug/DebugContext";

const KIND_LABEL: Record<DebugKind, string> = {
  info: "info",
  lab: "lab",
  model: "model",
  error: "error",
  http: "http",
  judge: "judge",
};

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

interface DebugFloatProps {
  /** Controlled open — when set, parent owns expand/collapse (mutex with results). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function DebugFloat({ open: openProp, onOpenChange }: DebugFloatProps = {}) {
  const { events, unreadErrors, clear, markSeen } = useDebugLog();
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const controlled = openProp !== undefined;
  const open = controlled ? openProp : uncontrolledOpen;
  const setOpen = (next: boolean) => {
    if (!controlled) setUncontrolledOpen(next);
    onOpenChange?.(next);
  };
  const [copied, setCopied] = useState(false);
  const titleId = useId();
  const logRef = useRef<HTMLDivElement>(null);
  const fabRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  // The FAB unmounts when the panel expands, so focus would otherwise fall to
  // <body>. One shot, set on the FAB click, so a programmatic open stays
  // focus-neutral — same guard as `ModelsFloat`.
  const focusOnOpen = useRef(false);

  useEffect(() => {
    if (open) markSeen();
  }, [open, markSeen, events.length]);

  // `owned` is false when Escape arrives from the composer: the panel is not
  // modal, so it closes silently and the caret stays where the reader put it.
  const collapse = useCallback(
    (owned: boolean) => {
      if (!controlled) setUncontrolledOpen(false);
      onOpenChange?.(false);
      if (owned) queueMicrotask(() => fabRef.current?.focus());
    },
    [controlled, onOpenChange],
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      collapse(panelRef.current?.contains(document.activeElement) ?? false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, collapse]);

  useEffect(() => {
    if (!open || !focusOnOpen.current) return;
    focusOnOpen.current = false;
    queueMicrotask(() => panelRef.current?.focus());
  }, [open]);

  // Context stores newest-first; reverse for chronological log + stick to bottom.
  const chronological = [...events].reverse();

  useEffect(() => {
    if (!open) return;
    const el = logRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [open, events.length]);

  const copy = async () => {
    const text = chronological
      .map((e) => `${formatTime(e.ts)}\t${e.kind}\t${e.message}`)
      .join("\n");
    try {
      await navigator.clipboard.writeText(text || "(пусто)");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="debug-float-root">
      {!open && (
        <button
          ref={fabRef}
          type="button"
          className="debug-float-fab"
          id="debug-float-fab"
          /* No `aria-expanded`/`aria-controls`: the FAB and the panel replace
             each other, so the pair would name an element that never coexists. */
          aria-label={
            unreadErrors > 0 ? `Отладка, ошибок: ${unreadErrors}` : "Отладка"
          }
          onClick={() => {
            focusOnOpen.current = true;
            setOpen(true);
          }}
        >
          Debug
          {unreadErrors > 0 && (
            <span className="debug-float-badge" aria-hidden="true">
              {unreadErrors}
            </span>
          )}
        </button>
      )}

      {open && (
        <aside
          ref={panelRef}
          id="debug-float-panel"
          className="debug-float"
          /* Same shape as the other two floats, so a screen reader announces
             all three the same way. Focus lands here, not on «Свернуть», so
             the title and the log read in order. */
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          tabIndex={-1}
        >
          <header className="debug-float-head">
            <h2 id={titleId} className="debug-float-title">
              Журнал
              <span className="debug-float-live" aria-hidden="true" />
            </h2>
            <div className="debug-float-actions">
              <button type="button" className="ghost-button" onClick={() => void copy()}>
                {copied ? "Скопировано" : "Копировать"}
              </button>
              <button type="button" className="ghost-button" onClick={clear}>
                Очистить
              </button>
              <button
                type="button"
                className="ghost-button"
                aria-label="Свернуть журнал отладки"
                onClick={() => collapse(true)}
              >
                Свернуть
              </button>
            </div>
          </header>
          <div
            ref={logRef}
            className="debug-float-log"
            role="log"
            aria-live="polite"
          >
            {chronological.length === 0 && (
              <p className="debug-float-empty">Пока пусто — события появятся при запросах.</p>
            )}
            {chronological.map((e) => (
              <div key={e.id} className="debug-float-line">
                <time className="debug-float-ts" dateTime={new Date(e.ts).toISOString()}>
                  {formatTime(e.ts)}
                </time>
                <span className={`debug-float-kind debug-float-kind--${e.kind}`}>
                  {KIND_LABEL[e.kind]}
                </span>
                <span className="debug-float-msg">{e.message}</span>
              </div>
            ))}
          </div>
        </aside>
      )}
    </div>
  );
}

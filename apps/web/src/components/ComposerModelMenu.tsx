import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

export type ComposerModelOption = { id: string; label: string };

type Props = {
  value: string;
  globalLabel: string;
  options: ComposerModelOption[];
  disabled?: boolean;
  onChange: (id: string) => void;
};

function shortModelLabel(id: string, label: string): string {
  if (!id) return label;
  if (id.startsWith("ollama/")) return id.slice("ollama/".length);
  const tail = id.includes("/") ? id.split("/").pop() || id : id;
  if (label && label !== id && label.length <= 28) return label;
  return tail.length > 26 ? `${tail.slice(0, 24)}…` : tail;
}

/**
 * Portal popup for composer model pin — native &lt;select&gt; hides long
 * `ollama/…` ids in the overcrowded options bar.
 */
export function ComposerModelMenu({
  value,
  globalLabel,
  options,
  disabled,
  onChange,
}: Props) {
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [box, setBox] = useState({ top: 0, left: 0, width: 280 });
  const uid = useId();

  const items = useMemo(() => {
    const local: ComposerModelOption[] = [];
    const cloud: ComposerModelOption[] = [];
    const seen = new Set<string>();
    for (const o of options) {
      if (!o.id || seen.has(o.id) || o.id === "auto") continue;
      seen.add(o.id);
      if (o.id.startsWith("ollama/")) local.push(o);
      else cloud.push(o);
    }
    return { local, cloud };
  }, [options]);

  const selectedLabel = value
    ? shortModelLabel(
        value,
        options.find((o) => o.id === value)?.label || value,
      )
    : `Общие · ${shortModelLabel("", globalLabel)}`;

  const place = () => {
    const el = btnRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const width = Math.min(Math.max(r.width, 300), Math.min(420, window.innerWidth - 16));
    const left = Math.min(Math.max(8, r.left), window.innerWidth - width - 8);
    const maxH = 320;
    const below = r.bottom + 6;
    const top = below + maxH > window.innerHeight - 8 ? Math.max(8, r.top - maxH - 6) : below;
    setBox({ top, left, width });
  };

  useEffect(() => {
    if (!open) return;
    place();
    const onDoc = (ev: PointerEvent) => {
      const t = ev.target as Node | null;
      if (btnRef.current?.contains(t) || menuRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setOpen(false);
    };
    const onRe = () => place();
    const t = window.setTimeout(() => {
      document.addEventListener("pointerdown", onDoc, true);
    }, 0);
    window.addEventListener("resize", onRe);
    window.addEventListener("scroll", onRe, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener("pointerdown", onDoc, true);
      window.removeEventListener("resize", onRe);
      window.removeEventListener("scroll", onRe, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const pick = (id: string) => {
    onChange(id);
    setOpen(false);
  };

  return (
    <div className="composer-model-picker">
      <span className="composer-options-label" id={`${uid}-label`}>
        Модель
      </span>
      <button
        ref={btnRef}
        type="button"
        id="composer-model-select"
        className="composer-model-menu-btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? uid : undefined}
        aria-labelledby={`${uid}-label`}
        title={value || globalLabel}
        disabled={disabled}
        data-local={value.startsWith("ollama/") ? "1" : undefined}
        onClick={() => {
          if (disabled) return;
          setOpen((v) => !v);
        }}
      >
        {value.startsWith("ollama/") ? (
          <span className="composer-model-menu-tag">с компа</span>
        ) : null}
        <code>{selectedLabel}</code>
      </button>
      {open
        ? createPortal(
            <div
              ref={menuRef}
              id={uid}
              className="composer-model-menu"
              role="listbox"
              aria-label="Выбор модели"
              style={{ top: box.top, left: box.left, width: box.width }}
            >
              <button
                type="button"
                role="option"
                aria-selected={!value}
                className={!value ? "composer-model-menu-item is-on" : "composer-model-menu-item"}
                onClick={() => pick("")}
              >
                <span className="composer-model-menu-item-kicker">Общие</span>
                <code>{globalLabel}</code>
              </button>
              {items.local.length > 0 ? (
                <p className="composer-model-menu-group" role="presentation">
                  С компа
                </p>
              ) : null}
              {items.local.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  role="option"
                  aria-selected={o.id === value}
                  className={
                    o.id === value ? "composer-model-menu-item is-on" : "composer-model-menu-item"
                  }
                  title={o.id}
                  onClick={() => pick(o.id)}
                >
                  <code>{shortModelLabel(o.id, o.label)}</code>
                </button>
              ))}
              {items.cloud.length > 0 ? (
                <p className="composer-model-menu-group" role="presentation">
                  Облако
                </p>
              ) : null}
              {items.cloud.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  role="option"
                  aria-selected={o.id === value}
                  className={
                    o.id === value ? "composer-model-menu-item is-on" : "composer-model-menu-item"
                  }
                  title={o.id}
                  onClick={() => pick(o.id)}
                >
                  <code>{shortModelLabel(o.id, o.label)}</code>
                </button>
              ))}
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

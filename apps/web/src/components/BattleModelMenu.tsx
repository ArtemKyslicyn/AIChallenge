import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

type Option = { id: string; label?: string };

type Props = {
  value: string;
  options: Option[];
  disabled?: boolean;
  ariaLabel: string;
  onChange: (id: string) => void;
};

/** In-page menu (portal) — native <select> mouseup hits the map/iframe and snaps shut. */
export function BattleModelMenu({ value, options, disabled, ariaLabel, onChange }: Props) {
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [box, setBox] = useState({ top: 0, left: 0, width: 240 });
  const uid = useId();
  const items = useMemo(() => {
    const seen = new Set<string>();
    const list: Option[] = [{ id: "auto", label: "auto (цепочка)" }];
    for (const o of options) {
      if (!o.id || seen.has(o.id) || o.id === "auto") continue;
      seen.add(o.id);
      list.push(o);
    }
    return list;
  }, [options]);

  const label = items.find((o) => o.id === value)?.label || value || "auto";

  const place = () => {
    const el = btnRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const width = Math.max(r.width, 260);
    const left = Math.min(r.left, window.innerWidth - width - 8);
    const below = r.bottom + 6;
    const maxH = 280;
    const top = below + maxH > window.innerHeight - 8 ? Math.max(8, r.top - maxH - 6) : below;
    setBox({ top, left: Math.max(8, left), width });
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
    // Next tick: ignore the opening click.
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

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className="civ-model-menu-btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? uid : undefined}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => {
          if (disabled) return;
          setOpen((v) => !v);
        }}
      >
        <code>{label}</code>
      </button>
      {open
        ? createPortal(
            <div
              ref={menuRef}
              id={uid}
              className="civ-model-menu"
              role="listbox"
              aria-label={ariaLabel}
              style={{ top: box.top, left: box.left, width: box.width }}
            >
              {items.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  role="option"
                  aria-selected={o.id === value}
                  className={o.id === value ? "civ-model-menu-item is-on" : "civ-model-menu-item"}
                  onClick={() => {
                    onChange(o.id);
                    setOpen(false);
                  }}
                >
                  <code>{o.label || o.id}</code>
                </button>
              ))}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

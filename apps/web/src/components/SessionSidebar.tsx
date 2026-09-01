import { useEffect, useRef } from "react";

import type { ChatHistoryItem } from "../api/client";

function formatWhen(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  const time = date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (sameDay) return time;
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "short" }) + ", " + time;
}

function titleFor(item: ChatHistoryItem): string {
  if (item.title?.trim()) return item.title.trim();
  if (item.message_count > 0) return "Без названия";
  return "Новый чат";
}

export function SessionSidebar({
  items,
  activeId,
  loading,
  open,
  onClose,
  onSelect,
  onNew,
}: {
  items: ChatHistoryItem[];
  activeId: string | null;
  loading: boolean;
  open: boolean;
  onClose: () => void;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      <div
        className={`sidebar-backdrop${open ? " open" : ""}`}
        onClick={onClose}
        aria-hidden={!open}
      />

      <aside
        id="chat-sidebar"
        className={`sidebar${open ? " open" : ""}`}
        aria-label="История чатов"
      >
        <div className="sidebar-head">
          <h2>Чаты</h2>
          <button type="button" className="ghost-button sidebar-close" onClick={onClose}>
            Закрыть
          </button>
        </div>

        <button type="button" className="sidebar-new" onClick={onNew}>
          + Новый чат
        </button>

        <div className="sidebar-list" ref={listRef}>
          {loading && (
            <p className="sidebar-empty">
              <span className="spinner" aria-hidden="true" /> Загрузка…
            </p>
          )}

          {!loading && items.length === 0 && (
            <p className="sidebar-empty">Пока нет сохранённых диалогов.</p>
          )}

          {!loading &&
            items.map((item) => {
              const active = item.id === activeId;
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`sidebar-item${active ? " active" : ""}`}
                  onClick={() => onSelect(item.id)}
                  aria-current={active ? "true" : undefined}
                >
                  <span className="sidebar-item-title">{titleFor(item)}</span>
                  <span className="sidebar-item-meta">
                    {formatWhen(item.created_at)}
                    {item.message_count > 0 && ` · ${item.message_count} сообщ.`}
                  </span>
                </button>
              );
            })}
        </div>
      </aside>
    </>
  );
}

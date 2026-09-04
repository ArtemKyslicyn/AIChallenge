import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";

/** Tabs inside the «Модели» float. */
export type ModelsTab = "ranking" | "feedback" | "studio";

/** Observation window in hours — passed straight to the Lab API `hours` query. */
export type ModelsWindowHours = 24 | 168;

const WINDOWS: ModelsWindowHours[] = [24, 168];

const WINDOW_LABEL: Record<ModelsWindowHours, string> = {
  24: "24 часа",
  168: "7 дней",
};

const TAB_ORDER: ModelsTab[] = ["studio", "ranking", "feedback"];

const TAB_LABEL: Record<ModelsTab, string> = {
  studio: "Студия",
  ranking: "Рейтинг",
  feedback: "Оценки",
};

/** Honest empty states while the real panels are not mounted yet (no «Скоро»). */
const TAB_EMPTY: Record<ModelsTab, string> = {
  studio: "Задайте запрос и сравните слабую, среднюю и сильную модели.",
  ranking: "Пока нет замеров. Отправьте пару сообщений в чат.",
  feedback:
    "Оценок пока нет. Кнопки «Полезно» / «Не полезно» есть под ответом в режиме «Один».",
};

/** What the shell tells a tab's content about itself. */
export interface ModelsTabContext {
  /** Currently selected window, in hours. */
  hours: ModelsWindowHours;
  /** True when this tab is selected; inactive panels stay mounted but hidden. */
  active: boolean;
}

/**
 * Tab content: a plain node, or a function of the shell context so a panel can
 * refetch when `hours` changes and stay idle while it is not `active`.
 */
export type ModelsTabContent = ReactNode | ((ctx: ModelsTabContext) => ReactNode);

interface ModelsFloatProps {
  /** Driven by the float-dock mutex in Chat.tsx. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Controlled window; omit to let the float own it (defaults to 24). */
  hours?: ModelsWindowHours;
  onHoursChange?: (hours: ModelsWindowHours) => void;
  /** Controlled tab; omit to let the float own it (defaults to "studio"). */
  tab?: ModelsTab;
  onTabChange?: (tab: ModelsTab) => void;
  /** Content of the «Студия» tab — Performance Studio. */
  studio?: ModelsTabContent;
  /** Content of the «Рейтинг» tab — ParetoPanel lands here. */
  ranking?: ModelsTabContent;
  /** Content of the «Оценки» tab — FeedbackStatsPanel lands here. */
  feedback?: ModelsTabContent;
}

function renderTab(content: ModelsTabContent | undefined, ctx: ModelsTabContext): ReactNode {
  if (content === undefined || content === null) return null;
  return typeof content === "function" ? content(ctx) : content;
}

function tabContent(
  id: ModelsTab,
  props: Pick<ModelsFloatProps, "studio" | "ranking" | "feedback">,
): ModelsTabContent | undefined {
  if (id === "studio") return props.studio;
  if (id === "ranking") return props.ranking;
  return props.feedback;
}

export function ModelsFloat({
  open,
  onOpenChange,
  hours: hoursProp,
  onHoursChange,
  tab: tabProp,
  onTabChange,
  studio,
  ranking,
  feedback,
}: ModelsFloatProps) {
  const titleId = useId();
  const fabRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const tabRefs = useRef<Partial<Record<ModelsTab, HTMLButtonElement | null>>>({});

  const [uncontrolledTab, setUncontrolledTab] = useState<ModelsTab>("studio");
  const tab = tabProp ?? uncontrolledTab;
  const selectTab = useCallback(
    (next: ModelsTab) => {
      if (tabProp === undefined) setUncontrolledTab(next);
      onTabChange?.(next);
    },
    [tabProp, onTabChange],
  );

  const [uncontrolledHours, setUncontrolledHours] = useState<ModelsWindowHours>(24);
  const hours = hoursProp ?? uncontrolledHours;
  const selectHours = useCallback(
    (next: ModelsWindowHours) => {
      if (hoursProp === undefined) setUncontrolledHours(next);
      onHoursChange?.(next);
    },
    [hoursProp, onHoursChange],
  );

  const collapse = useCallback(
    (owned: boolean) => {
      onOpenChange(false);
      if (owned) queueMicrotask(() => fabRef.current?.focus());
    },
    [onOpenChange],
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

  const focusOnOpen = useRef(false);
  useEffect(() => {
    if (!open || !focusOnOpen.current) return;
    focusOnOpen.current = false;
    queueMicrotask(() => panelRef.current?.focus());
  }, [open]);

  const onTabKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const index = TAB_ORDER.indexOf(tab);
    let next: ModelsTab | undefined;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      next = TAB_ORDER[(index + 1) % TAB_ORDER.length];
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      next = TAB_ORDER[(index - 1 + TAB_ORDER.length) % TAB_ORDER.length];
    } else if (e.key === "Home") {
      next = TAB_ORDER[0];
    } else if (e.key === "End") {
      next = TAB_ORDER[TAB_ORDER.length - 1];
    }
    if (!next) return;
    e.preventDefault();
    selectTab(next);
    const target = next;
    queueMicrotask(() => tabRefs.current[target]?.focus());
  };

  if (!open) {
    return (
      <button
        ref={fabRef}
        type="button"
        className="models-float-fab"
        id="models-float-fab"
        onClick={() => {
          focusOnOpen.current = true;
          onOpenChange(true);
        }}
      >
        Модели
      </button>
    );
  }

  const studioMode = tab === "studio";

  return (
    <aside
      ref={panelRef}
      id="models-float-panel"
      className={`models-float${studioMode ? " models-float--studio" : ""}`}
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      tabIndex={-1}
    >
      <header className="models-float-head">
        <h2 id={titleId} className="models-float-title">
          {studioMode ? "Performance Studio" : "Модели"}
        </h2>
        <div className="models-float-actions">
          {!studioMode && (
            <select
              className="models-float-window"
              aria-label="Период"
              value={hours}
              onChange={(e) => selectHours(Number(e.target.value) as ModelsWindowHours)}
            >
              {WINDOWS.map((w) => (
                <option key={w} value={w}>
                  {WINDOW_LABEL[w]}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            className="ghost-button"
            aria-label="Свернуть панель «Модели»"
            onClick={() => collapse(true)}
          >
            Свернуть
          </button>
        </div>
      </header>

      <div
        className="models-float-tabs"
        role="tablist"
        aria-label="Разделы"
        onKeyDown={onTabKeyDown}
      >
        {TAB_ORDER.map((id) => (
          <button
            key={id}
            ref={(el) => {
              tabRefs.current[id] = el;
            }}
            type="button"
            role="tab"
            id={`models-tab-${id}`}
            className="models-float-tab"
            aria-selected={tab === id}
            aria-controls={`models-panel-${id}`}
            tabIndex={tab === id ? 0 : -1}
            onClick={() => selectTab(id)}
          >
            {TAB_LABEL[id]}
          </button>
        ))}
      </div>

      {TAB_ORDER.map((id) => {
        const active = tab === id;
        const content = renderTab(tabContent(id, { studio, ranking, feedback }), {
          hours,
          active,
        });
        return (
          <div
            key={id}
            role="tabpanel"
            id={`models-panel-${id}`}
            className={`models-float-panel${id === "studio" ? " models-float-panel--studio" : ""}`}
            aria-labelledby={`models-tab-${id}`}
            tabIndex={0}
            hidden={!active}
          >
            {content ?? <p className="models-float-empty">{TAB_EMPTY[id]}</p>}
          </div>
        );
      })}
    </aside>
  );
}

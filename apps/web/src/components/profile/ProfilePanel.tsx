import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";

import {
  ApiError,
  authChangePassword,
  authLogin,
  authLogout,
  authPatchMe,
  authRegister,
  clearLocalSessionCache,
  createNewSession,
  fetchLiveModelPulse,
  fetchRagAdminEligible,
  fetchRagStats,
  listModels,
  patchRagSettings,
  setAuthToken,
  type AuthUserDto,
  type ModelCatalogItemDto,
  type RagStatsDto,
} from "../../api/client";
import { useAuthUser } from "../../auth/authUser";
import {
  loadGlobalChatPrefs,
  saveGlobalChatPrefs,
} from "../../chatPrefs/globalPrefs";
import type { ChatMode, GlobalChatPrefs, LanguageHint } from "../../chatPrefs/types";
import {
  CUSTOM_RULES_MAX_CHARS,
  PROMPT_CONTROLS,
  RESPONSE_TEMPLATES,
  type PromptControlId,
} from "../../promptControls";
import {
  loadProfileModelPrefs,
  saveProfileModelPrefs,
} from "../../profilePrefs";
import { GuestMcpPanel } from "../GuestMcpPanel";

export type ProfileSectionId =
  | "account"
  | "security"
  | "models"
  | "answers"
  | "chat"
  | "connections"
  | "stand"
  | "personalization"
  | "device"
  | "about";

const RAIL: { group: string; items: { id: ProfileSectionId; label: string }[] }[] = [
  {
    group: "Аккаунт",
    items: [
      { id: "account", label: "Аккаунт" },
      { id: "security", label: "Безопасность" },
    ],
  },
  {
    group: "По умолчанию",
    items: [
      { id: "models", label: "Модели" },
      { id: "answers", label: "Как отвечать" },
      { id: "chat", label: "По умолчанию" },
    ],
  },
  {
    group: "Подключения",
    items: [
      { id: "connections", label: "Подключения" },
      { id: "stand", label: "Состояние" },
    ],
  },
  {
    group: "На устройстве",
    items: [
      { id: "personalization", label: "Предпочтения" },
      { id: "device", label: "На этом устройстве" },
      { id: "about", label: "О продукте" },
    ],
  },
];

const LEADS: Record<ProfileSectionId, string> = {
  account: "Имя и почта. Выход из аккаунта.",
  security: "Смена пароля. Выход только с этого устройства.",
  models: "Избранные и модель по умолчанию для новых чатов.",
  answers: "Язык, тон и правила ответа по умолчанию.",
  chat: "Режим нового чата и свой сервер для новых диалогов.",
  connections: "Стендовая база знаний, свой MCP и внешний RAG через туннель.",
  stand: "Краткий статус сервиса. Полный пульс — во вкладке MCP.",
  personalization: "Активный стиль ответа. Полная настройка — в Агентах.",
  device: "Локальная история на этом браузере — не то же самое, что аккаунт.",
  about: "Чат, в котором видно модель. Коротко про свой MCP и набор.",
};

const AUTH_GATED = new Set<ProfileSectionId>([
  "security",
  "models",
  "answers",
  "chat",
  "connections",
  "stand",
  "personalization",
  "device",
]);

interface Props {
  open: boolean;
  onClose: () => void;
  initialSection?: ProfileSectionId;
  sessionId: string | null;
  onOpenMcp: () => void;
  onOpenAgents: () => void;
  onSessionReset?: (session: { id: string; access_token: string }) => void;
}

function readProfileQuery(): ProfileSectionId | null {
  try {
    const id = new URLSearchParams(window.location.search).get("profile");
    if (!id) return null;
    const known = RAIL.flatMap((g) => g.items.map((i) => i.id));
    return known.includes(id as ProfileSectionId) ? (id as ProfileSectionId) : null;
  } catch {
    return null;
  }
}

export function ProfilePanel({
  open,
  onClose,
  initialSection,
  sessionId,
  onOpenMcp,
  onOpenAgents,
  onSessionReset,
}: Props) {
  const titleId = useId();
  const { user, setUser, refresh } = useAuthUser();
  const loggedIn = Boolean(user && !user.anonymous && user.email);
  const [section, setSection] = useState<ProfileSectionId>(
    initialSection ?? readProfileQuery() ?? "account",
  );
  const [mobileDetail, setMobileDetail] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement as HTMLElement | null;
    const start = initialSection ?? readProfileQuery() ?? "account";
    setSection(start);
    setMobileDetail(false);
    const t = window.setTimeout(() => closeRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [open, initialSection]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      if (mobileDetail) {
        setMobileDetail(false);
        return;
      }
      onClose();
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [open, mobileDetail, onClose]);

  useEffect(() => {
    if (!open) {
      returnFocus.current?.focus?.();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const root = panelRef.current;
    if (!root) return;
    const focusable = () =>
      Array.from(
        root.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => el.offsetParent !== null || el === closeRef.current);

    const onTab = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const nodes = focusable();
      if (nodes.length === 0) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    root.addEventListener("keydown", onTab);
    return () => root.removeEventListener("keydown", onTab);
  }, [open, section, mobileDetail]);

  const pickSection = (id: ProfileSectionId) => {
    setSection(id);
    setMobileDetail(true);
  };

  if (!open) return null;

  const gated = !loggedIn && AUTH_GATED.has(section);

  return (
    <div className="profile-root">
      <button
        type="button"
        className="profile-backdrop"
        aria-label="Закрыть профиль"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        className="profile-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="profile-header">
          <div>
            <h1 id={titleId} className="profile-title">
              Профиль
            </h1>
            <p className="profile-eyebrow">
              {loggedIn ? user!.email : "не вошли"}
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="ghost-button profile-close"
            onClick={onClose}
          >
            Закрыть
          </button>
        </header>

        <div className={`profile-body${mobileDetail ? " is-detail" : ""}`}>
          <nav className="profile-rail" aria-label="Разделы профиля">
            {!loggedIn ? (
              <p className="profile-rail-note">
                После входа — модели, ответы, подключения
              </p>
            ) : null}
            {(loggedIn ? RAIL : RAIL.filter((g) => g.group === "Аккаунт")).map((group) => (
              <div key={group.group} className="profile-rail-group">
                <p className="profile-rail-group-label">{group.group}</p>
                <ul>
                  {group.items.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        className={
                          section === item.id
                            ? "profile-rail-item is-active"
                            : "profile-rail-item"
                        }
                        aria-current={section === item.id ? "page" : undefined}
                        onClick={() => pickSection(item.id)}
                      >
                        {item.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>

          <div className="profile-main">
            <button
              type="button"
              className="ghost-button profile-back"
              onClick={() => setMobileDetail(false)}
            >
              Назад
            </button>
            <h2 className="profile-section-title">
              {RAIL.flatMap((g) => g.items).find((i) => i.id === section)?.label}
            </h2>
            <p className="profile-section-lead">{LEADS[section]}</p>

            {gated ? (
              <div className="profile-gate">
                <p role="status">Войдите, чтобы открыть этот раздел</p>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => pickSection("account")}
                >
                  Войти
                </button>
              </div>
            ) : (
              <SectionBody
                section={section}
                user={user}
                loggedIn={loggedIn}
                sessionId={sessionId}
                setUser={setUser}
                refresh={refresh}
                onClose={onClose}
                onOpenMcp={() => {
                  onClose();
                  onOpenMcp();
                }}
                onOpenAgents={() => {
                  onClose();
                  onOpenAgents();
                }}
                onSessionReset={onSessionReset}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function SectionBody(props: {
  section: ProfileSectionId;
  user: AuthUserDto | null;
  loggedIn: boolean;
  sessionId: string | null;
  setUser: (u: AuthUserDto | null) => void;
  refresh: () => Promise<AuthUserDto>;
  onClose: () => void;
  onOpenMcp: () => void;
  onOpenAgents: () => void;
  onSessionReset?: (session: { id: string; access_token: string }) => void;
}): ReactNode {
  switch (props.section) {
    case "account":
      return (
        <AccountSection
          user={props.user}
          loggedIn={props.loggedIn}
          setUser={props.setUser}
        />
      );
    case "security":
      return <SecuritySection setUser={props.setUser} />;
    case "models":
      return <ModelsSection userId={props.user?.id ?? ""} />;
    case "answers":
      return <AnswersSection />;
    case "chat":
      return <ChatDefaultsSection />;
    case "connections":
      return (
        <div className="profile-connections guest-mcp-panel--compact">
          <RagStandSection />
          {props.sessionId ? (
            <GuestMcpPanel sessionId={props.sessionId} />
          ) : (
            <p className="guest-mcp-muted">Нет активной сессии чата для своего MCP.</p>
          )}
          <p className="guest-mcp-muted">
            Внешняя база: поднимите RAG MCP (туннель на{" "}
            <code>/mcp</code>) и вставьте URL сюда как свой сервер — tools{" "}
            <code>rag_search</code> / <code>rag_stats</code>.
          </p>
        </div>
      );
    case "stand":
      return <StandSection onOpenMcp={props.onOpenMcp} />;
    case "personalization":
      return (
        <div>
          <p className="guest-mcp-muted">
            Активный стиль ответа настраивается в Агентах.
          </p>
          <button type="button" className="text-link" onClick={props.onOpenAgents}>
            Открыть в Агентах
          </button>
        </div>
      );
    case "device":
      return (
        <DeviceSection
          onCleared={async () => {
            clearLocalSessionCache();
            const next = await createNewSession();
            props.onSessionReset?.(next);
          }}
        />
      );
    case "about":
      return (
        <div className="profile-about">
          <p>
            <strong>Чат, в котором видно модель</strong> — под каждым ответом видно, какая
            модель ответила.
          </p>
          <p className="guest-mcp-muted">
            Свой MCP подключается в Подключениях; вкладка MCP — статус стенда.
          </p>
          <a
            className="text-link"
            href="https://github.com/ArtemKyslicyn/aichallenge-mcp-kit"
            target="_blank"
            rel="noreferrer"
          >
            Набор для своего сервера
          </a>
        </div>
      );
    default:
      return null;
  }
}

function RagStandSection() {
  const [stats, setStats] = useState<RagStatsDto | null>(null);
  const [eligible, setEligible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const ac = new AbortController();
    void fetchRagStats(ac.signal)
      .then(setStats)
      .catch(() => setStats({ disabled: true, total_chunks: 0 }));
    void fetchRagAdminEligible(ac.signal)
      .then((r) => setEligible(r.eligible))
      .catch(() => setEligible(false));
    return () => ac.abort();
  }, []);

  const toggleLocal = async (on: boolean) => {
    setBusy(true);
    setError("");
    try {
      const next = await patchRagSettings({ local_embeddings: on });
      setStats(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="profile-rag-stand" aria-label="База знаний стенда">
      <h3 className="profile-subsection-title">База знаний стенда</h3>
      {stats?.disabled ? (
        <p className="guest-mcp-muted">Сервис базы сейчас недоступен.</p>
      ) : (
        <p className="guest-mcp-muted">
          Чанков: {stats?.total_chunks ?? "…"}
          {stats?.chunk_strategy ? ` · стратегия ${stats.chunk_strategy}` : ""}
          {stats?.embedding_provider ? ` · embed ${stats.embedding_provider}` : ""}
        </p>
      )}
      {eligible && (
        <label className="composer-toggle">
          <input
            type="checkbox"
            disabled={busy}
            checked={Boolean(stats?.local_embeddings_enabled)}
            onChange={(e) => void toggleLocal(e.target.checked)}
          />
          <span>Локальные эмбеддинги на сервере</span>
        </label>
      )}
      {error && <p className="alert">{error}</p>}
    </section>
  );
}

function AccountSection({
  user,
  loggedIn,
  setUser,
}: {
  user: AuthUserDto | null;
  loggedIn: boolean;
  setUser: (u: AuthUserDto | null) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setDisplayName(user?.display_name ?? "");
  }, [user?.display_name]);

  if (!loggedIn) {
    return (
      <form
        className="profile-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (busy) return;
          setBusy(true);
          setError("");
          void (mode === "register"
            ? authRegister(email.trim(), password)
            : authLogin(email.trim(), password)
          )
            .then((res) => {
              setAuthToken(res.access_token);
              setUser(res.user);
              setPassword("");
              setStatus("");
            })
            .catch((err) => {
              setError(err instanceof ApiError ? err.message : String(err));
            })
            .finally(() => setBusy(false));
        }}
      >
        <div className="auth-panel-tabs" role="tablist">
          <button
            type="button"
            className={mode === "login" ? "is-active" : ""}
            aria-selected={mode === "login"}
            onClick={() => setMode("login")}
          >
            Вход
          </button>
          <button
            type="button"
            className={mode === "register" ? "is-active" : ""}
            aria-selected={mode === "register"}
            onClick={() => setMode("register")}
          >
            Регистрация
          </button>
        </div>
        <label className="composer-field">
          <span>Email</span>
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label className="composer-field">
          <span>Пароль</span>
          <input
            type="password"
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
        </label>
        {error ? (
          <p className="guest-mcp-form-error" role="alert">
            {error}
          </p>
        ) : null}
        <button type="submit" className="primary-button" disabled={busy}>
          {mode === "register" ? "Создать" : "Войти"}
        </button>
      </form>
    );
  }

  return (
    <div className="profile-form">
      <p className="composer-field">
        <span>Email</span>
        <span aria-describedby="profile-email-ro">{user!.email}</span>
        <span id="profile-email-ro" className="guest-mcp-muted">
          только чтение
        </span>
      </p>
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (busy) return;
          setBusy(true);
          setError("");
          setStatus("");
          void authPatchMe(displayName.trim())
            .then((me) => {
              setUser(me);
              setStatus("Имя сохранено");
            })
            .catch((err) => {
              setError(err instanceof ApiError ? err.message : String(err));
            })
            .finally(() => setBusy(false));
        }}
      >
        <label className="composer-field">
          <span>Отображаемое имя</span>
          <input
            type="text"
            value={displayName}
            maxLength={120}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </label>
        {error ? (
          <p className="guest-mcp-form-error" role="alert">
            {error}
          </p>
        ) : null}
        {status ? (
          <p className="guest-mcp-muted" role="status">
            {status}
          </p>
        ) : null}
        <button type="submit" className="primary-button" disabled={busy}>
          Сохранить
        </button>
      </form>
      <button
        type="button"
        className="ghost-button"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          void authLogout()
            .then(() => {
              setUser({
                id: "",
                email: "",
                display_name: "",
                owner_key: "",
                anonymous: true,
              });
            })
            .finally(() => setBusy(false));
        }}
      >
        Выйти
      </button>
    </div>
  );
}

function SecuritySection({ setUser }: { setUser: (u: AuthUserDto | null) => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <div className="profile-form">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (busy) return;
          if (next !== again) {
            setError("Новый пароль и повтор не совпадают.");
            return;
          }
          setBusy(true);
          setError("");
          setStatus("");
          void authChangePassword(current, next)
            .then((res) => {
              setUser(res.user);
              setCurrent("");
              setNext("");
              setAgain("");
              setStatus("Пароль обновлён");
            })
            .catch((err) => {
              setError(err instanceof ApiError ? err.message : String(err));
            })
            .finally(() => setBusy(false));
        }}
      >
        <label className="composer-field">
          <span>Текущий пароль</span>
          <input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </label>
        <label className="composer-field">
          <span>Новый пароль</span>
          <input
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
            minLength={8}
          />
        </label>
        <label className="composer-field">
          <span>Ещё раз</span>
          <input
            type="password"
            autoComplete="new-password"
            value={again}
            onChange={(e) => setAgain(e.target.value)}
            required
            minLength={8}
          />
        </label>
        {error ? (
          <p className="guest-mcp-form-error" role="alert">
            {error}
          </p>
        ) : null}
        {status ? (
          <p className="guest-mcp-muted" role="status">
            {status}
          </p>
        ) : null}
        <button type="submit" className="primary-button" disabled={busy}>
          Сменить пароль
        </button>
      </form>
      <button
        type="button"
        className="ghost-button"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          void authLogout()
            .then(() => {
              setUser({
                id: "",
                email: "",
                display_name: "",
                owner_key: "",
                anonymous: true,
              });
            })
            .finally(() => setBusy(false));
        }}
      >
        Выйти на этом устройстве
      </button>
    </div>
  );
}

function ModelsSection({ userId }: { userId: string }) {
  const [models, setModels] = useState<ModelCatalogItemDto[]>([]);
  const [prefs, setPrefs] = useState(() => loadProfileModelPrefs(userId));
  const [global, setGlobal] = useState(() => loadGlobalChatPrefs());

  useEffect(() => {
    void listModels()
      .then(setModels)
      .catch(() => setModels([]));
  }, []);

  useEffect(() => {
    setPrefs(loadProfileModelPrefs(userId));
  }, [userId]);

  const persist = (next: typeof prefs) => {
    setPrefs(next);
    saveProfileModelPrefs(userId, next);
  };

  return (
    <div className="profile-form">
      <label className="composer-field">
        <span>Модель по умолчанию</span>
        <select
          value={prefs.defaultModelId || global.modelId || ""}
          onChange={(e) => {
            const id = e.target.value;
            persist({ ...prefs, defaultModelId: id });
            const g = { ...global, modelId: id };
            setGlobal(g);
            saveGlobalChatPrefs(g);
          }}
        >
          <option value="">Авто</option>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label || m.id}
            </option>
          ))}
        </select>
      </label>
      <ul className="profile-model-list">
        {models.map((m) => {
          const fav = prefs.favoriteIds.includes(m.id);
          return (
            <li key={m.id}>
              <button
                type="button"
                className="ghost-button"
                aria-pressed={fav}
                aria-label={`В избранное: ${m.label || m.id}`}
                onClick={() => {
                  const favoriteIds = fav
                    ? prefs.favoriteIds.filter((x) => x !== m.id)
                    : [...prefs.favoriteIds, m.id];
                  persist({ ...prefs, favoriteIds });
                }}
              >
                {fav ? "★" : "☆"} {m.label || m.id}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function AnswersSection() {
  const [global, setGlobal] = useState(() => loadGlobalChatPrefs());
  const patch = (partial: Partial<GlobalChatPrefs>) => {
    const next = { ...global, ...partial };
    setGlobal(next);
    saveGlobalChatPrefs(next);
  };

  return (
    <div className="profile-form">
      <label className="composer-field">
        <span>Язык ответа</span>
        <select
          value={global.languageHint}
          onChange={(e) => patch({ languageHint: e.target.value as LanguageHint })}
        >
          <option value="ru">Русский</option>
          <option value="en">English</option>
          <option value="">Без подсказки</option>
        </select>
      </label>
      <label className="composer-field">
        <span>Температура</span>
        <input
          type="number"
          min={0}
          max={2}
          step={0.1}
          value={global.temperature}
          onChange={(e) => patch({ temperature: Number(e.target.value) })}
        />
      </label>
      <label className="composer-toggle">
        <input
          type="checkbox"
          checked={global.reasoning}
          onChange={(e) => patch({ reasoning: e.target.checked })}
        />
        Reasoning
      </label>
      <label className="composer-field">
        <span>Шаблон</span>
        <select
          value={global.responseTemplateId}
          onChange={(e) =>
            patch({
              responseTemplateId: e.target.value as GlobalChatPrefs["responseTemplateId"],
            })
          }
        >
          {RESPONSE_TEMPLATES.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <div className="composer-options-chips" role="group" aria-label="Правила">
        {PROMPT_CONTROLS.map((c) => (
          <button
            key={c.id}
            type="button"
            className={
              global.promptControls[c.id as PromptControlId]
                ? "composer-chip is-active"
                : "composer-chip"
            }
            aria-pressed={global.promptControls[c.id as PromptControlId]}
            onClick={() =>
              patch({
                promptControls: {
                  ...global.promptControls,
                  [c.id]: !global.promptControls[c.id as PromptControlId],
                },
                responseTemplateId: "custom",
              })
            }
          >
            {c.label}
          </button>
        ))}
      </div>
      <label className="composer-field">
        <span>Свои правила</span>
        <textarea
          className="composer-rules-input"
          maxLength={CUSTOM_RULES_MAX_CHARS}
          value={global.customRulesText}
          onChange={(e) =>
            patch({ customRulesText: e.target.value, responseTemplateId: "custom" })
          }
        />
      </label>
    </div>
  );
}

function ChatDefaultsSection() {
  const [global, setGlobal] = useState(() => loadGlobalChatPrefs());
  // guestMcp default lives in session prefs default — store on global via unused field?
  // Spec: Guest MCP on for new chats — use session default in sessionPrefs DEFAULT.
  // We'll store a flag in localStorage alongside global.
  const [guestOn, setGuestOn] = useState(() => {
    try {
      return localStorage.getItem("aichallenge.guest_mcp_default") !== "0";
    } catch {
      return true;
    }
  });

  const setMode = (mode: ChatMode) => {
    const next = { ...global, defaultChatMode: mode };
    setGlobal(next);
    saveGlobalChatPrefs(next);
  };

  return (
    <div className="profile-form">
      <div className="composer-options-chips" role="group" aria-label="Режим нового чата">
        <button
          type="button"
          className={
            global.defaultChatMode === "single" || global.defaultChatMode === "lab"
              ? "composer-chip is-active"
              : "composer-chip"
          }
          aria-pressed={global.defaultChatMode === "single"}
          onClick={() => setMode("single")}
        >
          Обычный
        </button>
        <button
          type="button"
          className={global.defaultChatMode === "compare" ? "composer-chip is-active" : "composer-chip"}
          aria-pressed={global.defaultChatMode === "compare"}
          onClick={() => setMode("compare")}
        >
          Два рядом
        </button>
      </div>
      <p className="guest-mcp-muted">Один ответ · под ним видно модель</p>
      <label className="composer-toggle">
        <input
          type="checkbox"
          checked={guestOn}
          onChange={(e) => {
            const on = e.target.checked;
            setGuestOn(on);
            try {
              localStorage.setItem("aichallenge.guest_mcp_default", on ? "1" : "0");
            } catch {
              /* ignore */
            }
          }}
        />
        Свой MCP в новых чатах
      </label>
    </div>
  );
}

function StandSection({ onOpenMcp }: { onOpenMcp: () => void }) {
  const [line, setLine] = useState("Загрузка…");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    setBusy(true);
    void fetchLiveModelPulse()
      .then((pulse) => {
        const leader = pulse.ranking?.find((r) => !r.avoid);
        const when = "";
        setLine(
          leader
            ? `Стенд: ок · лидер ${leader.model_id}${when}`
            : `Стенд: данные получены${when}`,
        );
      })
      .catch(() => setLine("Стенд: не удалось обновить"))
      .finally(() => setBusy(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="profile-form">
      <p role="status">{busy ? "Обновляем…" : line}</p>
      <button type="button" className="ghost-button" onClick={refresh} disabled={busy}>
        Обновить
      </button>{" "}
      <button type="button" className="text-link" onClick={onOpenMcp}>
        Открыть вкладку MCP
      </button>
    </div>
  );
}

function DeviceSection({ onCleared }: { onCleared: () => Promise<void> }) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (confirmOpen) cancelRef.current?.focus();
  }, [confirmOpen]);

  return (
    <div className="profile-form">
      <p className="guest-mcp-muted">
        История чатов в этом браузере привязана к устройству. Аккаунт и память агентов не то же
        самое.
      </p>
      <button type="button" className="ghost-button" onClick={() => setConfirmOpen(true)}>
        Очистить историю на этом устройстве
      </button>
      {status ? (
        <p className="guest-mcp-muted" role="status">
          {status}
        </p>
      ) : null}
      {confirmOpen ? (
        <div
          className="profile-alertdialog"
          role="alertdialog"
          aria-labelledby="clear-local-title"
          aria-describedby="clear-local-desc"
        >
          <h3 id="clear-local-title">Очистить историю?</h3>
          <p id="clear-local-desc">
            Удалит список чатов в этом браузере. Аккаунт и память агентов не трогаем. Отменить
            нельзя.
          </p>
          <div className="profile-alertdialog-actions">
            <button
              ref={cancelRef}
              type="button"
              className="ghost-button"
              onClick={() => setConfirmOpen(false)}
            >
              Отмена
            </button>
            <button
              type="button"
              className="primary-button"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                void onCleared()
                  .then(() => {
                    setStatus("История на этом устройстве очищена");
                    setConfirmOpen(false);
                  })
                  .catch((err) => {
                    setStatus(err instanceof Error ? err.message : String(err));
                  })
                  .finally(() => setBusy(false));
              }}
            >
              Очистить
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

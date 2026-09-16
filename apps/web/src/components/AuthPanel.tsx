import { useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  authLogin,
  authLogout,
  authMe,
  authRegister,
  setAuthToken,
  type AuthUserDto,
} from "../api/client";

export function AuthPanel() {
  const [user, setUser] = useState<AuthUserDto | null>(null);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void authMe()
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        if (!cancelled) setUser({ id: "", email: "", display_name: "", owner_key: "", anonymous: true });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setStatus("");
    try {
      const res =
        mode === "register"
          ? await authRegister(email.trim(), password)
          : await authLogin(email.trim(), password);
      setAuthToken(res.access_token);
      setUser(res.user);
      setOpen(false);
      setPassword("");
      setStatus("");
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    try {
      await authLogout();
      setUser({ id: "", email: "", display_name: "", owner_key: "", anonymous: true });
    } finally {
      setBusy(false);
    }
  }

  const loggedIn = Boolean(user && !user.anonymous && user.email);

  return (
    <div className="auth-panel">
      {loggedIn ? (
        <div className="auth-panel-user">
          <span className="auth-panel-email" title={user!.email}>
            {user!.display_name || user!.email}
          </span>
          <button type="button" className="ghost-button auth-panel-btn" onClick={() => void logout()} disabled={busy}>
            Выйти
          </button>
        </div>
      ) : (
        <>
          <button
            type="button"
            className="ghost-button auth-panel-btn"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "Закрыть" : "Войти"}
          </button>
          {open ? (
            <form className="auth-panel-form" onSubmit={(e) => void submit(e)}>
              <p className="auth-panel-hint">Анонимный режим сохранён. Вход — claim памяти visitor→user.</p>
              <div className="auth-panel-tabs" role="tablist">
                <button
                  type="button"
                  className={mode === "login" ? "is-active" : ""}
                  onClick={() => setMode("login")}
                >
                  Вход
                </button>
                <button
                  type="button"
                  className={mode === "register" ? "is-active" : ""}
                  onClick={() => setMode("register")}
                >
                  Регистрация
                </button>
              </div>
              <label>
                Email
                <input
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </label>
              <label>
                Пароль
                <input
                  type="password"
                  autoComplete={mode === "register" ? "new-password" : "current-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  minLength={8}
                  required
                />
              </label>
              {status ? <p className="auth-panel-error" role="alert">{status}</p> : null}
              <button type="submit" className="agent-send-btn" disabled={busy}>
                {mode === "register" ? "Создать аккаунт" : "Войти"}
              </button>
            </form>
          ) : null}
        </>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";

import { useAuthUser } from "../auth/authUser";
import { ProfilePanel, type ProfileSectionId } from "./profile/ProfilePanel";

interface Props {
  sessionId: string | null;
  onOpenMcp: () => void;
  onOpenAgents: () => void;
  onSessionReset?: (session: { id: string; access_token: string }) => void;
}

export function openProfile(section?: ProfileSectionId): void {
  window.dispatchEvent(
    new CustomEvent("aichallenge:open-profile", { detail: { section } }),
  );
}

export function AuthPanel({
  sessionId,
  onOpenMcp,
  onOpenAgents,
  onSessionReset,
}: Props) {
  const { user, loading } = useAuthUser();
  const [open, setOpen] = useState(false);
  const [section, setSection] = useState<ProfileSectionId | undefined>(undefined);

  useEffect(() => {
    const onOpen = (ev: Event) => {
      const detail = (ev as CustomEvent<{ section?: ProfileSectionId }>).detail;
      setSection(detail?.section);
      setOpen(true);
    };
    window.addEventListener("aichallenge:open-profile", onOpen);
    return () => window.removeEventListener("aichallenge:open-profile", onOpen);
  }, []);

  useEffect(() => {
    try {
      const id = new URLSearchParams(window.location.search).get("profile");
      if (id) setOpen(true);
    } catch {
      /* ignore */
    }
  }, []);

  const loggedIn = Boolean(user && !user.anonymous && user.email);
  const label = loading
    ? "…"
    : loggedIn
      ? user!.display_name || user!.email
      : "Войти";

  return (
    <div className="auth-panel">
      <button
        type="button"
        className="ghost-button auth-panel-btn"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={loggedIn ? "Открыть профиль" : "Войти"}
        onClick={() => {
          setSection("account");
          setOpen(true);
        }}
      >
        <span className="auth-panel-email" title={loggedIn ? user!.email : undefined}>
          {label}
        </span>
      </button>
      <ProfilePanel
        open={open}
        onClose={() => setOpen(false)}
        initialSection={section}
        sessionId={sessionId}
        onOpenMcp={onOpenMcp}
        onOpenAgents={onOpenAgents}
        onSessionReset={onSessionReset}
      />
    </div>
  );
}

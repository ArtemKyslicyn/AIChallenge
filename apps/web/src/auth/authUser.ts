/** Shared auth user for topbar + Profile + Guest MCP. */

import { useCallback, useEffect, useState } from "react";

import { authMe, type AuthUserDto } from "../api/client";

type Listener = () => void;

const listeners = new Set<Listener>();

let cached: AuthUserDto | null = null;
let fetchPromise: Promise<AuthUserDto> | null = null;

function notify() {
  for (const listener of listeners) listener();
}

export function getCachedAuthUser(): AuthUserDto | null {
  return cached;
}

export function setCachedAuthUser(user: AuthUserDto | null): void {
  cached = user;
  notify();
}

export async function refreshAuthUser(): Promise<AuthUserDto> {
  if (!fetchPromise) {
    fetchPromise = authMe()
      .then((me) => {
        cached = me;
        notify();
        return me;
      })
      .catch(() => {
        const anon: AuthUserDto = {
          id: "",
          email: "",
          display_name: "",
          owner_key: "",
          anonymous: true,
        };
        cached = anon;
        notify();
        return anon;
      })
      .finally(() => {
        fetchPromise = null;
      });
  }
  return fetchPromise;
}

export function subscribeAuth(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useAuthUser(): {
  user: AuthUserDto | null;
  loading: boolean;
  refresh: () => Promise<AuthUserDto>;
  setUser: (user: AuthUserDto | null) => void;
} {
  const [user, setUserState] = useState<AuthUserDto | null>(cached);
  const [loading, setLoading] = useState(cached === null);

  useEffect(() => {
    return subscribeAuth(() => setUserState(cached));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void refreshAuthUser().finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const setUser = useCallback((next: AuthUserDto | null) => {
    setCachedAuthUser(next);
  }, []);

  const refresh = useCallback(() => refreshAuthUser(), []);

  return { user, loading, refresh, setUser };
}

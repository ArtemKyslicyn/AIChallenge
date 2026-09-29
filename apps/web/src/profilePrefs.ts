/** Per-user model favorites + default (client-only v1). */

export interface ProfileModelPrefs {
  favoriteIds: string[];
  defaultModelId: string;
}

const PREFIX = "aichallenge.profile_prefs.v1:";

function key(userId: string): string {
  return `${PREFIX}${userId || "anon"}`;
}

export function loadProfileModelPrefs(userId: string): ProfileModelPrefs {
  try {
    const raw = localStorage.getItem(key(userId));
    if (!raw) return { favoriteIds: [], defaultModelId: "" };
    const parsed = JSON.parse(raw) as Partial<ProfileModelPrefs>;
    return {
      favoriteIds: Array.isArray(parsed.favoriteIds)
        ? parsed.favoriteIds.filter((id): id is string => typeof id === "string")
        : [],
      defaultModelId: typeof parsed.defaultModelId === "string" ? parsed.defaultModelId : "",
    };
  } catch {
    return { favoriteIds: [], defaultModelId: "" };
  }
}

export function saveProfileModelPrefs(userId: string, prefs: ProfileModelPrefs): void {
  try {
    localStorage.setItem(key(userId), JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
}

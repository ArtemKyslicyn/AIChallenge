/** Shell mode: Chat vs Agents workspace (Day 6). */

export type ShellMode = "chat" | "agents";

const STORAGE_KEY = "aichallenge.shell_mode";

export function readShellMode(): ShellMode {
  if (typeof window === "undefined") return "chat";
  try {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("shell");
    if (q === "agents" || q === "chat") {
      writeShellMode(q);
      params.delete("shell");
      const next = `${window.location.pathname}${params.toString() ? `?${params}` : ""}${window.location.hash}`;
      window.history.replaceState({}, "", next);
      return q;
    }
    if (window.location.hash === "#agents") {
      writeShellMode("agents");
      return "agents";
    }
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw === "agents" || raw === "chat") return raw;
  } catch {
    /* ignore */
  }
  return "chat";
}

export function writeShellMode(mode: ShellMode): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}

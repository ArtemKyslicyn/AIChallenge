/** Shell mode: Chat | Agents workshop | Agent graph canvas. */

export type ShellMode = "chat" | "agents" | "graph";

const STORAGE_KEY = "aichallenge.shell_mode";

const VALID: ShellMode[] = ["chat", "agents", "graph"];

export function readShellMode(): ShellMode {
  if (typeof window === "undefined") return "chat";
  try {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("shell");
    if (q && VALID.includes(q as ShellMode)) {
      writeShellMode(q as ShellMode);
      params.delete("shell");
      const next = `${window.location.pathname}${params.toString() ? `?${params}` : ""}${window.location.hash}`;
      window.history.replaceState({}, "", next);
      return q as ShellMode;
    }
    if (window.location.hash === "#agents") {
      writeShellMode("agents");
      return "agents";
    }
    if (window.location.hash === "#graph" || window.location.hash === "#schema") {
      writeShellMode("graph");
      return "graph";
    }
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw && VALID.includes(raw as ShellMode)) return raw as ShellMode;
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

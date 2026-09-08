/** Per-agent run log / compose state (sessionStorage — survives tab switches). */

export interface RunLine {
  id: string;
  role: "user" | "assistant" | "error" | "status";
  text: string;
  modelId?: string | null;
  /** e.g. команда · parallel · abc123 */
  tag?: string;
  /** Display name when line is a handoff / peer message */
  speaker?: string;
}

export interface AgentSession {
  log: RunLine[];
  input: string;
  status: string;
  /** Postgres agent_dialogs.id when solo memory is active */
  dialogId?: string | null;
}

const KEY = "aichallenge.agent_sessions.v2";
const MAX_LOG = 80;

type SessionMap = Record<string, AgentSession>;

export function emptySession(): AgentSession {
  return { log: [], input: "", status: "", dialogId: null };
}

export function loadSessions(): SessionMap {
  try {
    // Prefer localStorage so history UI survives full browser restart;
    // Postgres remains source of truth and rehydrates on focus.
    const raw =
      localStorage.getItem(KEY) ??
      sessionStorage.getItem("aichallenge.agent_sessions.v1");
    if (!raw) return {};
    const parsed = JSON.parse(raw) as SessionMap;
    if (!parsed || typeof parsed !== "object") return {};
    const out: SessionMap = {};
    for (const [id, s] of Object.entries(parsed)) {
      if (!s || typeof s !== "object") continue;
      out[id] = {
        log: Array.isArray(s.log) ? s.log.slice(-MAX_LOG) : [],
        input: typeof s.input === "string" ? s.input : "",
        status: typeof s.status === "string" ? s.status : "",
        dialogId: typeof s.dialogId === "string" ? s.dialogId : null,
      };
    }
    return out;
  } catch {
    return {};
  }
}

export function saveSessions(map: SessionMap): void {
  try {
    const slim: SessionMap = {};
    for (const [id, s] of Object.entries(map)) {
      slim[id] = {
        log: (s.log || []).slice(-MAX_LOG),
        input: s.input || "",
        status: s.status || "",
        dialogId: s.dialogId ?? null,
      };
    }
    localStorage.setItem(KEY, JSON.stringify(slim));
  } catch {
    /* quota — ignore */
  }
}

export function ensureSession(map: SessionMap, id: string): AgentSession {
  return map[id] ?? emptySession();
}

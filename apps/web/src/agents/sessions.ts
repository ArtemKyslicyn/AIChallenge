/** Per-agent run log / compose state (sessionStorage — survives tab switches). */

export interface RunLine {
  id: string;
  role: "user" | "assistant" | "error" | "status";
  text: string;
  modelId?: string | null;
}

export interface AgentSession {
  log: RunLine[];
  input: string;
  status: string;
}

const KEY = "aichallenge.agent_sessions.v1";
const MAX_LOG = 80;

type SessionMap = Record<string, AgentSession>;

export function emptySession(): AgentSession {
  return { log: [], input: "", status: "" };
}

export function loadSessions(): SessionMap {
  try {
    const raw = sessionStorage.getItem(KEY);
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
      };
    }
    sessionStorage.setItem(KEY, JSON.stringify(slim));
  } catch {
    /* quota — ignore */
  }
}

export function ensureSession(map: SessionMap, id: string): AgentSession {
  return map[id] ?? emptySession();
}

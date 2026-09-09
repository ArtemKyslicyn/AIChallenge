/** Per-agent run log / compose state (sessionStorage — survives tab switches). */

export interface TokenMeter {
  request: number;
  history_before: number;
  history_after: number;
  completion: number;
  total: number;
  cost_proxy: number;
  truncation: {
    applied: boolean;
    dropped_messages: number;
    dropped_tokens_est: number;
    context_limit: number;
    budget: number;
  };
}

export interface RunLine {
  id: string;
  role: "user" | "assistant" | "error" | "status";
  text: string;
  modelId?: string | null;
  /** e.g. команда · parallel · abc123 */
  tag?: string;
  /** Display name when line is a handoff / peer message */
  speaker?: string;
  /** Day-8 approximate token meter (assistant lines). */
  tokens?: TokenMeter | null;
}

export interface AgentSession {
  log: RunLine[];
  input: string;
  status: string;
  /** Postgres agent_dialogs.id when solo memory is active */
  dialogId?: string | null;
  /** Optional context window override (tok approx) for Day-8 demos */
  contextLimit?: number | null;
}

const KEY = "aichallenge.agent_sessions.v2";
const MAX_LOG = 80;

type SessionMap = Record<string, AgentSession>;

export function emptySession(): AgentSession {
  return { log: [], input: "", status: "", dialogId: null, contextLimit: null };
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
        contextLimit:
          typeof s.contextLimit === "number" && s.contextLimit >= 64
            ? s.contextLimit
            : null,
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
        contextLimit: s.contextLimit ?? null,
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

/** Per-agent run log / compose state (sessionStorage — survives tab switches). */

export type ContextMode = "none" | "compress" | "sliding" | "facts";

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

export interface CompressionMeter {
  enabled: boolean;
  summary_used: boolean;
  summary_refreshed: boolean;
  summary_text: string;
  recent_kept: number;
  covered_by_summary: number;
  tokens_raw_est: number;
  tokens_compressed_est: number;
}

export interface ContextStrategyMeter {
  mode: ContextMode | string;
  recent_kept: number;
  dropped: number;
  facts: Record<string, string>;
  facts_updated: boolean;
  tokens_raw_est: number;
  tokens_strategy_est: number;
  summary_used?: boolean;
  summary_refreshed?: boolean;
  summary_text?: string;
  covered_by_summary?: number;
}

export interface BranchRef {
  draftId: string;
  dialogId: string;
  label: string;
  parentDialogId?: string | null;
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
  /** Server message id when synced from dialog */
  messageId?: string | null;
  /** Day-8 approximate token meter (assistant lines). */
  tokens?: TokenMeter | null;
  /** Day-9 compression stats (assistant lines). */
  compression?: CompressionMeter | null;
  /** Day-10 strategy meter */
  contextStrategy?: ContextStrategyMeter | null;
}

export interface AgentSession {
  log: RunLine[];
  input: string;
  status: string;
  /** Postgres agent_dialogs.id when solo memory is active */
  dialogId?: string | null;
  /** Optional context window override (tok approx) for Day-8 demos */
  contextLimit?: number | null;
  /** Day-10 mutually exclusive context mode */
  contextMode?: ContextMode;
  recentKeep?: number | null;
  summarizeEvery?: number | null;
  /** Last known rolling summary for UI */
  summaryText?: string | null;
  facts?: Record<string, string> | null;
  branches?: BranchRef[];
  /** When set, persist runs use this draft id instead of agent id (branch). */
  branchDraftId?: string | null;
}

const KEY = "aichallenge.agent_sessions.v3";
const MAX_LOG = 80;

const MODES: ContextMode[] = ["none", "compress", "sliding", "facts"];

function parseMode(raw: unknown, legacyCompress?: unknown): ContextMode {
  if (typeof raw === "string" && MODES.includes(raw as ContextMode)) {
    return raw as ContextMode;
  }
  if (legacyCompress) return "compress";
  return "none";
}

type SessionMap = Record<string, AgentSession>;

export function emptySession(): AgentSession {
  return {
    log: [],
    input: "",
    status: "",
    dialogId: null,
    contextLimit: null,
    contextMode: "none",
    recentKeep: 8,
    summarizeEvery: 10,
    summaryText: null,
    facts: null,
    branches: [],
    branchDraftId: null,
  };
}

export function loadSessions(): SessionMap {
  try {
    const raw =
      localStorage.getItem(KEY) ??
      localStorage.getItem("aichallenge.agent_sessions.v2") ??
      sessionStorage.getItem("aichallenge.agent_sessions.v1");
    if (!raw) return {};
    const parsed = JSON.parse(raw) as SessionMap;
    if (!parsed || typeof parsed !== "object") return {};
    const out: SessionMap = {};
    for (const [id, s] of Object.entries(parsed)) {
      if (!s || typeof s !== "object") continue;
      const legacy = s as AgentSession & { compress?: boolean };
      out[id] = {
        log: Array.isArray(s.log) ? s.log.slice(-MAX_LOG) : [],
        input: typeof s.input === "string" ? s.input : "",
        status: typeof s.status === "string" ? s.status : "",
        dialogId: typeof s.dialogId === "string" ? s.dialogId : null,
        contextLimit:
          typeof s.contextLimit === "number" && s.contextLimit >= 64
            ? s.contextLimit
            : null,
        contextMode: parseMode(s.contextMode, legacy.compress),
        recentKeep:
          typeof s.recentKeep === "number" && s.recentKeep >= 0 ? s.recentKeep : 8,
        summarizeEvery:
          typeof s.summarizeEvery === "number" && s.summarizeEvery >= 2
            ? s.summarizeEvery
            : 10,
        summaryText: typeof s.summaryText === "string" ? s.summaryText : null,
        facts:
          s.facts && typeof s.facts === "object" && !Array.isArray(s.facts)
            ? (s.facts as Record<string, string>)
            : null,
        branches: Array.isArray(s.branches) ? s.branches : [],
        branchDraftId: typeof s.branchDraftId === "string" ? s.branchDraftId : null,
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
        contextMode: s.contextMode ?? "none",
        recentKeep: s.recentKeep ?? 8,
        summarizeEvery: s.summarizeEvery ?? 10,
        summaryText: s.summaryText ?? null,
        facts: s.facts ?? null,
        branches: s.branches ?? [],
        branchDraftId: s.branchDraftId ?? null,
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

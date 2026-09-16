/**
 * API client.
 *
 * Chat history is shown only from this browser's encrypted-local cache
 * (session tokens in localStorage, bound to visitor id). Server history
 * enriches titles/counts for owned sessions only — never lists foreign chats.
 */

import { getVisitorId } from "../visitor";

export type Role = "user" | "assistant" | "system";

/**
 * Which stage of the FrugalGPT cascade produced an answer.
 *
 * Never null on the wire: `"off"` is the honest answer for every turn the
 * cascade did not take part in, which is all of them while it is switched off.
 * Optional here only because the probe endpoint builds its own `message_end`
 * frames and has no cascade to report.
 */
export type CascadeStage = "off" | "cheap" | "escalated";

export interface MessageDto {
  id: string;
  role: Role;
  content: string;
  model_id: string | null;
  created_at: string;
  /** Vote already stored for this message; `null`/absent when nobody voted. */
  feedback?: FeedbackValue | null;
  /** Carried with the history so the escalation badge survives a reload. */
  cascade_stage?: CascadeStage;
}

export interface SessionCredentials {
  id: string;
  access_token: string;
}

export interface SessionSummaryDto {
  id: string;
  title: string | null;
  created_at: string;
  message_count: number;
}

export interface ChatHistoryItem extends SessionSummaryDto {
  canOpen: boolean;
}

export type ChatEvent =
  | { type: "model"; model_id: string }
  | { type: "token"; text: string }
  | {
      type: "message_end";
      message_id: string | null;
      content: string;
      model_id: string;
      cascade_stage?: CascadeStage;
    }
  | { type: "error"; message: string }
  | { type: "tool_start"; name: string; call_id: string }
  | {
      type: "tool_result";
      name: string;
      call_id: string;
      status: string;
      media_url?: string | null;
      provider_label?: string | null;
      error?: string | null;
    }
  | {
      type: "comic_start";
      comic_id: string;
      title: string;
      panel_count: number;
      characters: { id: string; name: string; look: string }[];
      layout?: "single_page" | "per_panel";
    }
  | {
      type: "comic_panel";
      comic_id: string;
      index: number;
      status: string;
      text_mode: string;
      image_url?: string | null;
      speaker?: string | null;
      dialogue?: string | null;
      caption?: string | null;
      error?: string | null;
    }
  | { type: "comic_end"; comic_id: string; ok_count: number; fail_count: number };

const BASE = import.meta.env.VITE_API_URL || "/api/v1";
const STORE_KEY = "aichallenge.session_store";
const LEGACY_SESSION_KEY = "aichallenge.session";
const STORE_VERSION = 2;

/** Mirrors the server default for MAX_MESSAGE_CHARS, for client-side feedback
 *  only — the server is still the authority and answers 422 past the limit. */
export const MAX_MESSAGE_CHARS = 8000;

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

interface StoredSession extends SessionCredentials {
  created_at: string;
  title?: string | null;
}

interface SessionStore {
  version: number;
  /** Must match ``aichallenge.visitor_id`` — otherwise the cache is wiped. */
  visitorId: string;
  activeId: string;
  items: Record<string, StoredSession>;
}

function visitorHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "X-Visitor-Id": getVisitorId() };
  try {
    const token = localStorage.getItem("aichallenge.auth_token");
    if (token) headers["X-Auth-Token"] = token;
  } catch {
    /* ignore */
  }
  return headers;
}

export interface AuthUserDto {
  id: string;
  email: string;
  display_name: string;
  owner_key: string;
  anonymous: boolean;
}

export interface AuthTokenResponseDto {
  access_token: string;
  token_type: string;
  user: AuthUserDto;
}

export function getAuthToken(): string | null {
  try {
    return localStorage.getItem("aichallenge.auth_token");
  } catch {
    return null;
  }
}

export function setAuthToken(token: string | null): void {
  try {
    if (token) localStorage.setItem("aichallenge.auth_token", token);
    else localStorage.removeItem("aichallenge.auth_token");
  } catch {
    /* ignore */
  }
}

export function authMe(signal?: AbortSignal): Promise<AuthUserDto> {
  return request<AuthUserDto>("/auth/me", { signal });
}

export function authRegister(
  email: string,
  password: string,
  displayName = "",
): Promise<AuthTokenResponseDto> {
  return request<AuthTokenResponseDto>("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      display_name: displayName,
    }),
  });
}

export function authLogin(email: string, password: string): Promise<AuthTokenResponseDto> {
  return request<AuthTokenResponseDto>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password, display_name: "" }),
  });
}

export async function authLogout(): Promise<void> {
  try {
    await request<{ ok: boolean }>("/auth/logout", { method: "POST", body: "{}" });
  } finally {
    setAuthToken(null);
  }
}

export interface PreferenceProfileDto {
  id: string;
  name: string;
  style: string;
  format: string;
  constraints: string;
  is_active: boolean;
}

export interface ExpertLensDto {
  id: string;
  label: string;
  system_addendum: string;
}

export function listPreferenceProfiles(
  signal?: AbortSignal,
): Promise<PreferenceProfileDto[]> {
  return request<PreferenceProfileDto[]>("/personalization/profiles", { signal });
}

export function activatePreferenceProfile(
  profileId: string,
): Promise<PreferenceProfileDto> {
  return request<PreferenceProfileDto>(
    `/personalization/profiles/${encodeURIComponent(profileId)}/activate`,
    { method: "POST", body: "{}" },
  );
}

export function createPreferenceProfile(payload: {
  name: string;
  style?: string;
  format?: string;
  constraints?: string;
  activate?: boolean;
}): Promise<PreferenceProfileDto> {
  return request<PreferenceProfileDto>("/personalization/profiles", {
    method: "POST",
    body: JSON.stringify({
      name: payload.name,
      style: payload.style || "",
      format: payload.format || "",
      constraints: payload.constraints || "",
      activate: Boolean(payload.activate),
    }),
  });
}

export function updatePreferenceProfile(
  profileId: string,
  payload: {
    name: string;
    style?: string;
    format?: string;
    constraints?: string;
    activate?: boolean;
  },
): Promise<PreferenceProfileDto> {
  return request<PreferenceProfileDto>(
    `/personalization/profiles/${encodeURIComponent(profileId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        name: payload.name,
        style: payload.style || "",
        format: payload.format || "",
        constraints: payload.constraints || "",
        activate: Boolean(payload.activate),
      }),
    },
  );
}

export function listExpertLenses(signal?: AbortSignal): Promise<ExpertLensDto[]> {
  return request<ExpertLensDto[]>("/personalization/lenses", { signal });
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body?.error?.message ?? body?.detail ?? `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

/** Default JSON request timeout — avoids infinite boot spinner on network hangs. */
const REQUEST_TIMEOUT_MS = 30_000;

function mergeAbortSignals(signals: AbortSignal[]): AbortSignal | undefined {
  const active = signals.filter(Boolean);
  if (active.length === 0) return undefined;
  if (active.length === 1) return active[0];
  if (typeof AbortSignal.any === "function") return AbortSignal.any(active);
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  for (const signal of active) {
    if (signal.aborted) {
      controller.abort();
      return controller.signal;
    }
    signal.addEventListener("abort", onAbort, { once: true });
  }
  return controller.signal;
}

function requestTimeoutSignal(timeoutMs: number): AbortSignal {
  if (typeof AbortSignal.timeout === "function") return AbortSignal.timeout(timeoutMs);
  const controller = new AbortController();
  const id = window.setTimeout(() => controller.abort(new DOMException("Timeout", "TimeoutError")), timeoutMs);
  controller.signal.addEventListener("abort", () => window.clearTimeout(id), { once: true });
  return controller.signal;
}

async function send(
  path: string,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const timeoutSignal = requestTimeoutSignal(timeoutMs);
  const signal = mergeAbortSignals([init.signal, timeoutSignal].filter(Boolean) as AbortSignal[]);

  const response = await fetch(`${BASE}${path}`, {
    ...init,
    signal,
    headers: {
      "Content-Type": "application/json",
      ...visitorHeaders(),
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) throw new ApiError(await readError(response), response.status);
  return response;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<T> {
  return (await send(path, init, timeoutMs)).json() as Promise<T>;
}

/** Same request, for an endpoint that answers `204` — there is no body to parse. */
async function requestNoContent(
  path: string,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<void> {
  await send(path, init, timeoutMs);
}

function emptyStore(visitorId: string): SessionStore {
  return { version: STORE_VERSION, visitorId, activeId: "", items: {} };
}

function isStoredSession(value: unknown): value is StoredSession {
  if (!value || typeof value !== "object") return false;
  const row = value as StoredSession;
  return Boolean(row.id && row.access_token && row.created_at);
}

function sanitizeItems(items: Record<string, StoredSession>): Record<string, StoredSession> {
  const clean: Record<string, StoredSession> = {};
  for (const [id, row] of Object.entries(items)) {
    if (!isStoredSession(row) || row.id !== id) continue;
    clean[id] = row;
  }
  return clean;
}

/** Drop cache from another visitor profile or tempered copy-paste. */
function assertStoreOwner(store: SessionStore, visitorId: string): SessionStore | null {
  if (store.visitorId !== visitorId) return null;
  if (store.version !== STORE_VERSION) {
    return {
      version: STORE_VERSION,
      visitorId,
      activeId: store.activeId,
      items: sanitizeItems(store.items),
    };
  }
  return store;
}

function loadStore(): SessionStore {
  const visitorId = getVisitorId();

  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as SessionStore;
      if (parsed?.items && typeof parsed.items === "object") {
        const owned = assertStoreOwner(
          {
            version: parsed.version ?? 1,
            visitorId: parsed.visitorId ?? "",
            activeId: parsed.activeId ?? "",
            items: parsed.items,
          },
          visitorId,
        );
        if (owned) {
          const items = sanitizeItems(owned.items);
          const activeId = owned.activeId && items[owned.activeId] ? owned.activeId : "";
          return { ...owned, visitorId, activeId, items };
        }
        saveStore(emptyStore(visitorId));
        return emptyStore(visitorId);
      }
    }
  } catch {
    // fall through to migration
  }

  try {
    const legacy = localStorage.getItem(LEGACY_SESSION_KEY);
    if (legacy) {
      const creds = JSON.parse(legacy) as SessionCredentials;
      if (creds?.id && creds?.access_token) {
        const store: SessionStore = {
          version: STORE_VERSION,
          visitorId,
          activeId: creds.id,
          items: {
            [creds.id]: {
              ...creds,
              created_at: new Date().toISOString(),
            },
          },
        };
        saveStore(store);
        localStorage.removeItem(LEGACY_SESSION_KEY);
        return store;
      }
    }
  } catch {
    // ignored
  }

  return emptyStore(visitorId);
}

function saveStore(store: SessionStore): void {
  const visitorId = getVisitorId();
  const payload: SessionStore = {
    version: STORE_VERSION,
    visitorId,
    activeId: store.activeId,
    items: sanitizeItems(store.items),
  };
  if (payload.activeId && !payload.items[payload.activeId]) {
    payload.activeId = "";
  }
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(payload));
  } catch {
    // Private browsing: the session still works for this page view.
  }
}

function upsertSession(store: SessionStore, session: StoredSession): SessionStore {
  const next: SessionStore = {
    ...store,
    activeId: session.id,
    items: { ...store.items, [session.id]: session },
  };
  saveStore(next);
  return next;
}

let pending: Promise<SessionCredentials> | null = null;

async function validateSession(creds: SessionCredentials): Promise<boolean> {
  try {
    await request(`/sessions/${creds.id}`, {
      headers: { "X-Session-Token": creds.access_token },
    });
    return true;
  } catch (error) {
    if (isNotFound(error)) return false;
    throw error;
  }
}

function createSessionInternal(): Promise<SessionCredentials> {
  if (!pending) {
    pending = request<SessionCredentials>("/sessions", {
      method: "POST",
      body: JSON.stringify({}),
    })
      .then((session) => {
        const stored: StoredSession = {
          ...session,
          created_at: new Date().toISOString(),
        };
        upsertSession(loadStore(), stored);
        return session;
      })
      .finally(() => {
        pending = null;
      });
  }
  return pending;
}

/**
 * Reuses the stored session when it still exists on the server.
 * After a DB reset the localStorage id is a ghost → 404; drop it and mint a new one.
 */
export async function ensureSession(): Promise<SessionCredentials> {
  getVisitorId();
  const store = loadStore();
  const active = store.activeId ? store.items[store.activeId] : null;
  if (active) {
    if (await validateSession(active)) return active;
    const nextItems = { ...store.items };
    delete nextItems[active.id];
    saveStore({ ...store, activeId: "", items: nextItems });
  }
  return createSessionInternal();
}

export async function createNewSession(): Promise<SessionCredentials> {
  getVisitorId();
  pending = null;
  return createSessionInternal();
}

export function switchSession(sessionId: string): SessionCredentials | null {
  const store = loadStore();
  const item = store.items[sessionId];
  if (!item?.access_token) return null;
  saveStore({ ...store, activeId: sessionId });
  return item;
}

export function forgetActiveSession(): void {
  const store = loadStore();
  if (!store.activeId) return;
  const nextItems = { ...store.items };
  delete nextItems[store.activeId];
  saveStore({ ...store, activeId: "", items: nextItems });
}

/** @deprecated use forgetActiveSession */
export function forgetSession(): void {
  forgetActiveSession();
}

/**
 * Sidebar history: **local cache only** (sessions with a token in this browser).
 * Server metadata is merged only for those ids — never exposes other chats.
 */
export async function listChatHistory(): Promise<ChatHistoryItem[]> {
  const store = loadStore();
  const localSessions = Object.values(store.items).filter((row) => row.access_token);
  if (localSessions.length === 0) return [];

  const remoteById = new Map<string, SessionSummaryDto>();
  try {
    const remote = await request<SessionSummaryDto[]>("/sessions/history");
    for (const row of remote) {
      if (store.items[row.id]?.access_token) {
        remoteById.set(row.id, row);
      }
    }
  } catch {
    // Offline or API error — local titles still work.
  }

  return localSessions
    .map((local) => {
      const remote = remoteById.get(local.id);
      return {
        id: local.id,
        title: remote?.title ?? local.title ?? null,
        created_at: local.created_at,
        message_count: remote?.message_count ?? 0,
        canOpen: true,
      };
    })
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
}

export function touchSessionTitle(sessionId: string, title: string): void {
  const store = loadStore();
  const item = store.items[sessionId];
  if (!item) return;
  upsertSession(store, { ...item, title: title.slice(0, 120) });
}

export function listMessages(session: SessionCredentials): Promise<MessageDto[]> {
  const store = loadStore();
  const owned = store.items[session.id];
  if (!owned || owned.access_token !== session.access_token) {
    return Promise.reject(new ApiError("Сессия недоступна в этом браузере.", 403));
  }
  return request<MessageDto[]>(`/sessions/${session.id}/messages`, {
    headers: { "X-Session-Token": session.access_token },
  });
}

function parseFrame(raw: string): ChatEvent | null {
  let name = "";
  let data = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!name || !data) return null;
  try {
    return { type: name, ...JSON.parse(data) } as ChatEvent;
  } catch {
    return null;
  }
}

export async function sendMessageSSE(
  session: SessionCredentials,
  content: string,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
  options: { model?: string } = {},
): Promise<void> {
  const store = loadStore();
  const owned = store.items[session.id];
  if (!owned || owned.access_token !== session.access_token) {
    throw new ApiError("Сессия недоступна в этом браузере.", 403);
  }

  const response = await fetch(`${BASE}/sessions/${session.id}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Token": session.access_token,
      ...visitorHeaders(),
    },
    body: JSON.stringify({
      content,
      ...(options.model !== undefined ? { model: options.model } : {}),
    }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new ApiError(await readError(response), response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const event = parseFrame(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (event) onEvent(event);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export interface ModelCapabilitiesDto {
  temperature: boolean;
  max_tokens: boolean;
  stop: boolean;
  reasoning: boolean;
}

export interface ModelCatalogItemDto {
  id: string;
  label: string;
  capabilities: ModelCapabilitiesDto;
}

export interface ProbeGenerationDto {
  temperature?: number;
  max_tokens?: number;
  stop?: string[];
  prompt_format?: boolean;
  prompt_length?: boolean;
  prompt_stop?: boolean;
  reasoning?: boolean;
}

export interface ProbeResultDto {
  content: string;
  model_id: string;
}

export function listModels(): Promise<ModelCatalogItemDto[]> {
  return request<ModelCatalogItemDto[]>("/llm/models");
}

export type HarnessLeaderboardRow = {
  rank: number | null;
  model_id: string;
  model_label: string;
  harness: string | null;
  profile: string | null;
  passed: number | null;
  total: number | null;
  pct: number | null;
  steps: number | null;
  tokens: number | null;
  in_chain: boolean;
  matched: boolean;
};

export type HarnessBoardRow = {
  rank: number;
  harness: string;
  profile: string | null;
  model_label: string;
  passed: number;
  total: number;
  pct: number;
  steps: number | null;
  tokens: number | null;
  in_chain: boolean;
  linked_model_ids: string[];
};

export type HarnessLeaderboard = {
  task_set: string;
  total_tasks: number;
  source_url: string;
  landing_url: string;
  updated_at: string;
  coverage?: {
    connected: number;
    matched: number;
    unmatched: number;
    board_rows: number;
  };
  rows: HarnessLeaderboardRow[];
  board?: HarnessBoardRow[];
  refreshed?: boolean;
};

export function fetchHarnessLeaderboard(
  signal?: AbortSignal,
): Promise<HarnessLeaderboard> {
  return request<HarnessLeaderboard>("/benchmarks/leaderboard", { signal });
}

export function refreshHarnessLeaderboard(
  signal?: AbortSignal,
): Promise<HarnessLeaderboard> {
  return request<HarnessLeaderboard>("/benchmarks/refresh", {
    method: "POST",
    signal,
  });
}

export interface LabPresetDto {
  id: string;
  title: string;
  category: string;
  difficulty: string;
  task: string;
  golden_answer: string;
  golden_hint: string;
  rubric: string;
}

export function listLabPresets(): Promise<LabPresetDto[]> {
  return request<LabPresetDto[]>("/lab/presets");
}

export function probeComplete(
  prompt: string,
  options: { model: string } & ProbeGenerationDto,
  signal?: AbortSignal,
): Promise<ProbeResultDto> {
  return request<ProbeResultDto>(
    "/llm/complete",
    {
      method: "POST",
      body: JSON.stringify({ prompt, stream: false, ...options }),
      signal,
    },
    240_000,
  );
}

export interface AgentDefinitionDto {
  name: string;
  system_prompt: string;
  preferred_model: string;
  temperature: number | null;
  max_tokens: number | null;
}

export interface AgentDialogMessageDto {
  id: string;
  role: string;
  content: string;
  model_id?: string | null;
  created_at: string;
}

export interface AgentWorkshopRunResultDto {
  content: string;
  model_id: string;
  dialog_id?: string | null;
  messages?: AgentDialogMessageDto[] | null;
  tokens?: {
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
  } | null;
  compression?: {
    enabled: boolean;
    summary_used: boolean;
    summary_refreshed: boolean;
    summary_text: string;
    recent_kept: number;
    covered_by_summary: number;
    tokens_raw_est: number;
    tokens_compressed_est: number;
  } | null;
  context_strategy?: {
    mode: string;
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
  } | null;
}

export interface AgentDialogDto {
  id: string;
  client_draft_id: string;
  name: string;
  messages: AgentDialogMessageDto[];
  updated_at: string;
  summary_text?: string;
  summary_until_count?: number;
  facts?: Record<string, string>;
  working_memory?: Record<string, unknown>;
  parent_dialog_id?: string | null;
  branch_label?: string | null;
  forked_from_message_id?: string | null;
}

export interface AgentTaskStateDto {
  stage?: string;
  step?: string;
  expected_action?: string;
  paused?: boolean;
  goal?: string;
  resume_brief?: string;
}

export interface AgentMemorySnapshotDto {
  short_term: AgentDialogMessageDto[];
  working: {
    goal?: string;
    checklist?: string[];
    scratch?: Record<string, string>;
    task?: AgentTaskStateDto;
  };
  long_term: {
    profile?: Record<string, string>;
    decisions?: string[];
    knowledge?: Record<string, string>;
  };
}

export interface AgentMemoryWriteDto {
  layer?: "working" | "long_term";
  kind?: string;
  key?: string;
  value?: string;
  clientDraftId?: string;
  chatText?: string;
  dialogName?: string;
  dialogSystemPrompt?: string;
}

export interface AgentMemoryWriteResultDto extends AgentMemorySnapshotDto {
  applied?: {
    layer: string;
    kind: string;
    key: string;
    value: string;
  };
  label?: string;
}

export interface AgentWorkshopRunOptions {
  clientDraftId?: string;
  dialogId?: string | null;
  /** Persist turns in Postgres and continue with history (solo). */
  persist?: boolean;
  /** Day-8 context window budget override (approx tokens). */
  contextLimit?: number | null;
  /** Day-10 mutually exclusive mode. */
  contextMode?: "none" | "compress" | "sliding" | "facts";
  /** Day-9 compat alias → compress */
  compress?: boolean;
  recentKeep?: number | null;
  summarizeEvery?: number | null;
  includeWorkingMemory?: boolean;
  includeLongTermMemory?: boolean;
  expertLensId?: string | null;
  signal?: AbortSignal;
}

/** Day-6 workshop: encapsulated agent run (not `/llm/complete`). */
export function runAgentWorkshop(
  definition: AgentDefinitionDto,
  message: string,
  options?: AbortSignal | AgentWorkshopRunOptions,
): Promise<AgentWorkshopRunResultDto> {
  const opts: AgentWorkshopRunOptions =
    options && typeof options === "object" && "aborted" in options
      ? { signal: options as AbortSignal }
      : (options as AgentWorkshopRunOptions | undefined) ?? {};
  const body: Record<string, unknown> = { definition, message };
  if (opts.persist) {
    body.persist = true;
    if (opts.clientDraftId) body.client_draft_id = opts.clientDraftId;
    if (opts.dialogId) body.dialog_id = opts.dialogId;
  }
  if (opts.contextLimit != null && opts.contextLimit >= 64) {
    body.context_limit = opts.contextLimit;
  }
  const mode = opts.contextMode ?? (opts.compress ? "compress" : "none");
  if (mode && mode !== "none") {
    body.context_mode = mode;
  }
  if (mode === "compress" || mode === "sliding" || mode === "facts") {
    if (opts.recentKeep != null) body.recent_keep = opts.recentKeep;
  }
  if (mode === "compress" && opts.summarizeEvery != null) {
    body.summarize_every = opts.summarizeEvery;
  }
  if (opts.includeWorkingMemory === false) {
    body.include_working_memory = false;
  }
  if (opts.includeLongTermMemory === false) {
    body.include_long_term_memory = false;
  }
  if (opts.expertLensId) {
    body.expert_lens_id = opts.expertLensId;
  }
  return request<AgentWorkshopRunResultDto>(
    "/agent-workshop/run",
    {
      method: "POST",
      body: JSON.stringify(body),
      signal: opts.signal,
    },
    240_000,
  );
}

export function getAgentMemory(
  clientDraftId?: string | null,
  signal?: AbortSignal,
): Promise<AgentMemorySnapshotDto> {
  const q = clientDraftId
    ? `?client_draft_id=${encodeURIComponent(clientDraftId)}`
    : "";
  return request<AgentMemorySnapshotDto>(`/agent-workshop/memory${q}`, { signal });
}

export function writeAgentMemory(
  write: AgentMemoryWriteDto,
  signal?: AbortSignal,
): Promise<AgentMemoryWriteResultDto> {
  return request<AgentMemoryWriteResultDto>("/agent-workshop/memory/write", {
    method: "POST",
    body: JSON.stringify({
      layer: write.layer || null,
      kind: write.kind || null,
      key: write.key || "",
      value: write.value || "",
      client_draft_id: write.clientDraftId || null,
      chat_text: write.chatText || null,
      dialog_name: write.dialogName || null,
      dialog_system_prompt: write.dialogSystemPrompt || null,
    }),
    signal,
  });
}

export interface AgentTaskEventResultDto {
  working: AgentMemorySnapshotDto["working"];
  task: AgentTaskStateDto;
  label: string;
  dialog_id?: string | null;
}

export function postAgentTaskEvent(
  payload: {
    event: string;
    clientDraftId: string;
    goal?: string;
    step?: string;
    expectedAction?: string;
    resumeBrief?: string;
    dialogName?: string;
    dialogSystemPrompt?: string;
  },
  signal?: AbortSignal,
): Promise<AgentTaskEventResultDto> {
  return request<AgentTaskEventResultDto>("/agent-workshop/task", {
    method: "POST",
    body: JSON.stringify({
      event: payload.event,
      client_draft_id: payload.clientDraftId,
      goal: payload.goal || "",
      step: payload.step || "",
      expected_action: payload.expectedAction || "",
      resume_brief: payload.resumeBrief || "",
      dialog_name: payload.dialogName || null,
      dialog_system_prompt: payload.dialogSystemPrompt || null,
    }),
    signal,
  });
}

export async function forkAgentDialog(
  dialogId: string,
  body: { from_message_id: string; client_draft_id: string; label?: string },
  signal?: AbortSignal,
): Promise<AgentDialogDto> {
  return request<AgentDialogDto>(
    `/agent-workshop/dialogs/${encodeURIComponent(dialogId)}/fork`,
    {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    },
  );
}

export async function getAgentDialogByDraft(
  clientDraftId: string,
  signal?: AbortSignal,
): Promise<AgentDialogDto | null> {
  try {
    return await request<AgentDialogDto>(
      `/agent-workshop/dialogs/by-draft/${encodeURIComponent(clientDraftId)}`,
      { signal },
    );
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export function clearAgentDialogByDraft(
  clientDraftId: string,
  signal?: AbortSignal,
): Promise<AgentDialogDto> {
  return request<AgentDialogDto>(
    `/agent-workshop/dialogs/by-draft/${encodeURIComponent(clientDraftId)}/clear`,
    { method: "POST", signal },
  );
}

export type AgentGraphRunEvent =
  | { type: "graph_start"; name?: string; order: string[]; start_id: string }
  | { type: "node_start"; node_id: string; kind: string; label: string }
  | {
      type: "node_end";
      node_id: string;
      kind: string;
      label: string;
      content: string;
      model_id: string | null;
      degraded?: boolean;
    }
  | {
      type: "node_retry";
      node_id: string;
      kind: string;
      label: string;
      attempt: number;
      preferred_model: string;
      reason: string;
    }
  | {
      type: "model_switch";
      node_id: string;
      from_model: string;
      to_model: string;
      reason: string;
    }
  | {
      type: "node_degraded";
      node_id: string;
      kind: string;
      label: string;
      message: string;
    }
  | { type: "done"; content: string; end_ids: string[] }
  | { type: "error"; message: string; node_id?: string };

function parseGraphFrame(raw: string): AgentGraphRunEvent | null {
  const lines = raw.split("\n");
  let event = "message";
  let data = "";
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    const payload = JSON.parse(data) as Record<string, unknown>;
    if (event === "graph_start") {
      return {
        type: "graph_start",
        name: typeof payload.name === "string" ? payload.name : undefined,
        order: Array.isArray(payload.order) ? (payload.order as string[]) : [],
        start_id: String(payload.start_id || ""),
      };
    }
    if (event === "node_start") {
      return {
        type: "node_start",
        node_id: String(payload.node_id || ""),
        kind: String(payload.kind || ""),
        label: String(payload.label || ""),
      };
    }
    if (event === "node_retry") {
      return {
        type: "node_retry",
        node_id: String(payload.node_id || ""),
        kind: String(payload.kind || ""),
        label: String(payload.label || ""),
        attempt: Number(payload.attempt) || 0,
        preferred_model: String(payload.preferred_model || "auto"),
        reason: String(payload.reason || ""),
      };
    }
    if (event === "model_switch") {
      return {
        type: "model_switch",
        node_id: String(payload.node_id || ""),
        from_model: String(payload.from_model || ""),
        to_model: String(payload.to_model || ""),
        reason: String(payload.reason || ""),
      };
    }
    if (event === "node_degraded") {
      return {
        type: "node_degraded",
        node_id: String(payload.node_id || ""),
        kind: String(payload.kind || ""),
        label: String(payload.label || ""),
        message: String(payload.message || "ошибка"),
      };
    }
    if (event === "node_end") {
      return {
        type: "node_end",
        node_id: String(payload.node_id || ""),
        kind: String(payload.kind || ""),
        label: String(payload.label || ""),
        content: String(payload.content || ""),
        model_id: payload.model_id == null ? null : String(payload.model_id),
        degraded: Boolean(payload.degraded),
      };
    }
    if (event === "done") {
      return {
        type: "done",
        content: String(payload.content || ""),
        end_ids: Array.isArray(payload.end_ids) ? (payload.end_ids as string[]) : [],
      };
    }
    if (event === "error") {
      return {
        type: "error",
        message: String(payload.message || "Ошибка"),
        node_id: payload.node_id ? String(payload.node_id) : undefined,
      };
    }
  } catch {
    return null;
  }
  return null;
}

/** SSE events from POST /agent-battle/run. */
export type AgentBattleEvent =
  | {
      type: "battle_start";
      arena_id: string;
      name: string;
      seed: number;
      max_rounds: number;
      cast: { id: string; name: string }[];
      world: Record<string, unknown>;
    }
  | { type: "round_start"; round: number; world: Record<string, unknown> }
  | { type: "phase"; round: number; phase: string }
  | {
      type: "agent_done";
      round: number;
      phase: string;
      agent_id: string;
      name: string;
      content: string;
      model_id: string | null;
      skipped?: boolean;
      skip_reason?: string;
    }
  | {
      type: "verdict";
      round: number;
      red_line?: boolean;
      rationale: string;
      model_id: string | null;
      scores: { agent_id: string; points: number; notes?: string }[];
      world: Record<string, unknown>;
      delta?: Record<string, unknown>;
    }
  | { type: "world_update"; round: number; world: Record<string, unknown>; delta?: Record<string, unknown> }
  | {
      type: "battle_done";
      aborted?: boolean;
      leaderboard: { agent_id: string; name: string; points: number }[];
      goals_revealed?: { agent_id: string; hidden_goal: string }[];
      world: Record<string, unknown>;
    }
  | { type: "error"; message: string }
  | { type: "heartbeat"; round: number; phase: string | null };

function parseBattleFrame(raw: string): AgentBattleEvent | null {
  const lines = raw.split("\n");
  let event = "message";
  let data = "";
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    const payload = JSON.parse(data) as Record<string, unknown>;
    if (event === "battle_start") {
      return {
        type: "battle_start",
        arena_id: String(payload.arena_id || ""),
        name: String(payload.name || ""),
        seed: Number(payload.seed) || 0,
        max_rounds: Number(payload.max_rounds) || 1,
        cast: Array.isArray(payload.cast)
          ? (payload.cast as { id: string; name: string }[])
          : [],
        world: (payload.world as Record<string, unknown>) || {},
      };
    }
    if (event === "round_start") {
      return {
        type: "round_start",
        round: Number(payload.round) || 0,
        world: (payload.world as Record<string, unknown>) || {},
      };
    }
    if (event === "phase") {
      return {
        type: "phase",
        round: Number(payload.round) || 0,
        phase: String(payload.phase || ""),
      };
    }
    if (event === "agent_done") {
      return {
        type: "agent_done",
        round: Number(payload.round) || 0,
        phase: String(payload.phase || ""),
        agent_id: String(payload.agent_id || ""),
        name: String(payload.name || ""),
        content: String(payload.content || ""),
        model_id: payload.model_id == null ? null : String(payload.model_id),
        skipped: Boolean(payload.skipped),
        skip_reason:
          payload.skip_reason == null ? undefined : String(payload.skip_reason),
      };
    }
    if (event === "verdict") {
      return {
        type: "verdict",
        round: Number(payload.round) || 0,
        red_line: Boolean(payload.red_line),
        rationale: String(payload.rationale || ""),
        model_id: payload.model_id == null ? null : String(payload.model_id),
        scores: Array.isArray(payload.scores)
          ? (payload.scores as { agent_id: string; points: number; notes?: string }[])
          : [],
        world: (payload.world as Record<string, unknown>) || {},
        delta:
          payload.delta && typeof payload.delta === "object"
            ? (payload.delta as Record<string, unknown>)
            : undefined,
      };
    }
    if (event === "world_update") {
      return {
        type: "world_update",
        round: Number(payload.round) || 0,
        world: (payload.world as Record<string, unknown>) || {},
        delta:
          payload.delta && typeof payload.delta === "object"
            ? (payload.delta as Record<string, unknown>)
            : undefined,
      };
    }
    if (event === "battle_done") {
      return {
        type: "battle_done",
        aborted: Boolean(payload.aborted),
        leaderboard: Array.isArray(payload.leaderboard)
          ? (payload.leaderboard as {
              agent_id: string;
              name: string;
              points: number;
            }[])
          : [],
        goals_revealed: Array.isArray(payload.goals_revealed)
          ? (payload.goals_revealed as { agent_id: string; hidden_goal: string }[])
          : undefined,
        world: (payload.world as Record<string, unknown>) || {},
      };
    }
    if (event === "error") {
      return { type: "error", message: String(payload.message || "Ошибка") };
    }
    if (event === "heartbeat") {
      return {
        type: "heartbeat",
        round: Number(payload.round) || 0,
        phase: payload.phase == null ? null : String(payload.phase),
      };
    }
  } catch {
    return null;
  }
  return null;
}

/** POST /agent-battle/run — competing personas over SSE. */
export async function runAgentBattleSSE(
  arena: unknown,
  onEvent: (event: AgentBattleEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BASE}/agent-battle/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...visitorHeaders(),
    },
    body: JSON.stringify({ arena }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new ApiError(await readError(response), response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = parseBattleFrame(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (frame) onEvent(frame);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

/** POST /agent-studio/run — SSE execution of a client graph. */
export async function runAgentGraphSSE(
  message: string,
  graph: { name?: string; nodes: unknown[]; edges: unknown[] },
  onEvent: (event: AgentGraphRunEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BASE}/agent-studio/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...visitorHeaders(),
    },
    body: JSON.stringify({ message, graph }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new ApiError(await readError(response), response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = parseGraphFrame(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (frame) onEvent(frame);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

/**
 * `GET /api/v1/lab/pareto` — aggregates per `model_id` over a time window.
 *
 * Shape is the locked prep contract (D9): `p50_ttft_ms`, `p50_total_ms` and
 * `avg_cost_proxy` are nullable (unknown cost proxy / no samples), so the UI
 * must render a dash instead of `NaN`.
 */
export interface LabParetoModelDto {
  model_id: string;
  n: number;
  success_rate: number;
  /** Mean judge verdict 0..1 — null when nothing was judged, never 0. */
  avg_quality: number | null;
  /** How many runs that mean is over. Shown beside it, never on its own. */
  judged_n: number;
  p50_ttft_ms: number | null;
  p50_total_ms: number | null;
  avg_cost_proxy: number | null;
  score: number;
}

/** One window of the cascade — `null` when it never ran, so nothing is drawn. */
export interface LabCascadeDto {
  total: number;
  cheap: number;
  escalated: number;
  escalation_rate: number;
}

export interface LabParetoDto {
  formula: string;
  hours: number;
  models: LabParetoModelDto[];
  cascade?: LabCascadeDto | null;
}

/** Open endpoint (prep D5) — no session token, visitor header as everywhere else. */
export function getLabPareto(hours: number, signal?: AbortSignal): Promise<LabParetoDto> {
  return request<LabParetoDto>(`/lab/pareto?hours=${encodeURIComponent(String(hours))}`, {
    signal,
  });
}

/**
 * `POST /api/v1/messages/{id}/feedback` — one thumb per assistant message.
 *
 * Prep D9 body/response shape; prep D6 auth: the message's own session token
 * plus the visitor header `request` already attaches. A wrong token, a missing
 * message and a foreign session all answer 404, so the UI shows one error.
 */
export type FeedbackValue = "up" | "down";

export interface MessageFeedbackDto {
  message_id: string;
  value: FeedbackValue;
}

export function postMessageFeedback(
  session: SessionCredentials,
  messageId: string,
  value: FeedbackValue,
  signal?: AbortSignal,
): Promise<MessageFeedbackDto> {
  return request<MessageFeedbackDto>(`/messages/${encodeURIComponent(messageId)}/feedback`, {
    method: "POST",
    headers: { "X-Session-Token": session.access_token },
    body: JSON.stringify({ value }),
    signal,
  });
}

/**
 * `DELETE /api/v1/messages/{id}/feedback` — take the vote back.
 *
 * The way out of a mis-click, and what `aria-pressed` on the thumbs already
 * promises. Same auth as the POST, and idempotent: retracting a vote that is
 * not there answers `204` too, so the caller never has to know whether its own
 * optimistic retraction had already landed. Resolves with nothing — after this
 * the message simply has no vote.
 */
export function deleteMessageFeedback(
  session: SessionCredentials,
  messageId: string,
  signal?: AbortSignal,
): Promise<void> {
  return requestNoContent(`/messages/${encodeURIComponent(messageId)}/feedback`, {
    method: "DELETE",
    headers: { "X-Session-Token": session.access_token },
    signal,
  });
}

/**
 * `GET /api/v1/lab/feedback-stats` — thumbs aggregated per `model_id`.
 *
 * `penalized` means the router temporarily pushes the model down the candidate
 * list (prep D7 — a reorder, never a ban).
 */
export interface LabFeedbackModelDto {
  model_id: string;
  ups: number;
  downs: number;
  down_rate: number;
  penalized: boolean;
}

export interface LabFeedbackStatsDto {
  hours: number;
  models: LabFeedbackModelDto[];
}

/** Open endpoint (prep D5) — no session token, visitor header as everywhere else. */
export function getLabFeedbackStats(
  hours: number,
  signal?: AbortSignal,
): Promise<LabFeedbackStatsDto> {
  return request<LabFeedbackStatsDto>(
    `/lab/feedback-stats?hours=${encodeURIComponent(String(hours))}`,
    { signal },
  );
}

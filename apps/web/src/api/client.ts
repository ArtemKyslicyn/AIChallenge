/**
 * API client.
 *
 * Chat history is shown only from this browser's encrypted-local cache
 * (session tokens in localStorage, bound to visitor id). Server history
 * enriches titles/counts for owned sessions only — never lists foreign chats.
 */

import { getVisitorId } from "../visitor";

export type Role = "user" | "assistant" | "system";

export interface MessageDto {
  id: string;
  role: Role;
  content: string;
  model_id: string | null;
  created_at: string;
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
  | { type: "message_end"; message_id: string | null; content: string; model_id: string }
  | { type: "error"; message: string };

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
  return { "X-Visitor-Id": getVisitorId() };
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body?.error?.message ?? body?.detail ?? `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...visitorHeaders(),
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) throw new ApiError(await readError(response), response.status);
  return (await response.json()) as T;
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

export function probeComplete(
  prompt: string,
  options: { model: string } & ProbeGenerationDto,
  signal?: AbortSignal,
): Promise<ProbeResultDto> {
  return request<ProbeResultDto>("/llm/complete", {
    method: "POST",
    body: JSON.stringify({ prompt, stream: false, ...options }),
    signal,
  });
}

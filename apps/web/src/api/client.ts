/**
 * API client.
 *
 * The chat endpoint answers with SSE over a POST body, which rules out
 * EventSource, so the stream is read from fetch and parsed by hand.
 */

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

export type ChatEvent =
  | { type: "model"; model_id: string }
  | { type: "token"; text: string }
  | { type: "message_end"; message_id: string | null; content: string; model_id: string }
  | { type: "error"; message: string };

const BASE = import.meta.env.VITE_API_URL || "/api/v1";
const SESSION_KEY = "aichallenge.session";

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
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!response.ok) throw new ApiError(await readError(response), response.status);
  return (await response.json()) as T;
}

function loadStoredSession(): SessionCredentials | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SessionCredentials;
    return parsed?.id && parsed?.access_token ? parsed : null;
  } catch {
    return null;
  }
}

function storeSession(session: SessionCredentials): void {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    // Private browsing: the session still works for this page view.
  }
}

let pending: Promise<SessionCredentials> | null = null;

function createSession(): Promise<SessionCredentials> {
  if (!pending) {
    pending = request<SessionCredentials>("/sessions", {
      method: "POST",
      body: JSON.stringify({}),
    })
      .then((session) => {
        storeSession(session);
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
  const stored = loadStoredSession();
  if (stored) {
    try {
      await request(`/sessions/${stored.id}`, {
        headers: { "X-Session-Token": stored.access_token },
      });
      return stored;
    } catch (error) {
      if (!isNotFound(error)) throw error;
      forgetSession();
    }
  }
  return createSession();
}

export function forgetSession(): void {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    // ignored
  }
}

export function listMessages(session: SessionCredentials): Promise<MessageDto[]> {
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
): Promise<void> {
  const response = await fetch(`${BASE}/sessions/${session.id}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Token": session.access_token,
    },
    body: JSON.stringify({ content }),
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
    // A frame can straddle two network chunks, so decode incrementally and
    // only consume complete "\n\n"-delimited blocks.
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
